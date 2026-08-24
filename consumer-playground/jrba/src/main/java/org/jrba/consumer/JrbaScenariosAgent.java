package org.jrba.consumer;

import static org.jrba.rulesengine.constants.FactTypeConstants.RULE_TYPE;

import jade.core.AID;
import jade.core.behaviours.OneShotBehaviour;
import jade.core.behaviours.Behaviour;
import jade.lang.acl.ACLMessage;
import java.util.List;
import org.jrba.agentmodel.behaviour.ListenForControllerObjects;
import org.jrba.agentmodel.domain.AbstractAgent;
import org.jrba.rulesengine.RulesController;
import org.jrba.rulesengine.rule.AgentBasicRule;
import org.jrba.rulesengine.rule.AgentRuleDescription;
import org.jrba.rulesengine.rest.domain.RuleSetRest;
import org.jrba.rulesengine.ruleset.RuleSet;
import org.jrba.rulesengine.ruleset.RuleSetFacts;
import org.jrba.utils.yellowpages.YellowPagesRegister;

/**
 * Extended JRBA integration probe: runs four sequential scenarios against the
 * JRBA rules engine bound to the migrated JADE platform.
 *
 * S1 - facts-driven rule (positive and negative branch)
 * S2 - multiple rules in one rule set executed in priority order
 * S3 - multiple rule sets routed by index, missing index degrades gracefully
 * S4 - JADE interop: ACLMessage carried as a fact + DF registration/search
 */
public final class JrbaScenariosAgent extends AbstractAgent {

    @Override
    protected void setup() {
        setRulesController(new RulesController<>());
        super.setup();
    }

    @Override
    protected List<Behaviour> prepareStartingBehaviours() {
        return List.of(new OneShotBehaviour() {
            @Override
            public void action() {
                System.out.println("JRBA_TEST_STARTED");
                try {
                    runScenario1();
                    runScenario2();
                    runScenario3();
                    runScenario4();
                    System.out.println("JRBA_BEHAVIOR_EXECUTED");
                    System.out.println("JRBA_TEST_PASSED");
                } catch (Throwable failure) {
                    exitCode = 1;
                    System.out.println("JRBA_TEST_FAILED");
                } finally {
                    doDelete();
                }
            }
        });
    }

    @Override
    protected void runStartingBehaviours() {
        addBehaviour(new ListenForControllerObjects(
                this, prepareStartingBehaviours(), getObjectsNumber()));
    }

    @SuppressWarnings({ "rawtypes", "unchecked" })
    private RulesController controller() {
        return getRulesController();
    }

    private RuleSet newRuleSet(String name) {
        RuleSetRest rest = new RuleSetRest();
        rest.setName(name);
        rest.setRules(List.of());
        return new RuleSet(rest);
    }

    // ------------------------------------------------------------------
    // S1 - facts-driven rule
    // ------------------------------------------------------------------
    private void runScenario1() {
        System.out.println("JRBA_S1_STARTED");
        ThresholdRule rule = new ThresholdRule();
        RuleSet ruleSet = newRuleSet("S1_RULE_SET");
        ruleSet.getAgentRules().add(rule);
        controller().getRuleSets().put(1, ruleSet);

        RuleSetFacts low = new RuleSetFacts(1);
        low.put(RULE_TYPE, "FACT_THRESHOLD_RULE");
        low.put("input-value", 7);
        controller().fire(low);
        if (rule.ruleExecuted) {
            throw new IllegalStateException("rule executed below threshold");
        }
        System.out.println("JRBA_S1_RULE_SKIPPED");

        RuleSetFacts high = new RuleSetFacts(1);
        high.put(RULE_TYPE, "FACT_THRESHOLD_RULE");
        high.put("input-value", 21);
        controller().fire(high);
        if (!rule.ruleExecuted) {
            throw new IllegalStateException("rule not executed above threshold");
        }
        if (!Integer.valueOf(42).equals(high.get("result"))) {
            throw new IllegalStateException("rule did not compute expected result");
        }
        System.out.println("JRBA_S1_RULE_EXECUTED");
        System.out.println("JRBA_S1_PASSED");
    }

    // ------------------------------------------------------------------
    // S2 - multiple rules, priority order
    // ------------------------------------------------------------------
    private void runScenario2() {
        System.out.println("JRBA_S2_STARTED");
        StringBuilder order = new StringBuilder();
        OrderRule p10 = new OrderRule(10, "P10", order);
        OrderRule p20 = new OrderRule(20, "P20", order);
        OrderRule p30 = new OrderRule(30, "P30", order);
        RuleSet ruleSet = newRuleSet("S2_RULE_SET");
        ruleSet.getAgentRules().add(p10);
        ruleSet.getAgentRules().add(p20);
        ruleSet.getAgentRules().add(p30);
        controller().getRuleSets().put(2, ruleSet);

        RuleSetFacts facts = new RuleSetFacts(2);
        facts.put(RULE_TYPE, "MULTI_ORDER_RULE");
        controller().fire(facts);

        if (!(p10.executed && p20.executed && p30.executed)) {
            throw new IllegalStateException("not all ordered rules executed");
        }
        System.out.println("JRBA_S2_ALL_EXECUTED");
        String actualOrder = order.toString();
        if (actualOrder.endsWith(", ")) {
            actualOrder = actualOrder.substring(0, actualOrder.length() - 2);
        }
        if (!"P10, P20, P30".equals(actualOrder)) {
            throw new IllegalStateException("unexpected execution order: " + order);
        }
        System.out.println("JRBA_S2_ORDER_OK");
        System.out.println("JRBA_S2_PASSED");
    }

    // ------------------------------------------------------------------
    // S3 - multiple rule sets routed by index
    // ------------------------------------------------------------------
    private void runScenario3() {
        System.out.println("JRBA_S3_STARTED");
        SetScopedRule rs0Rule = new SetScopedRule("RS_ZERO_RULE");
        SetScopedRule rs1Rule = new SetScopedRule("RS_ONE_RULE");
        RuleSet rs0 = newRuleSet("S3_RS0");
        rs0.getAgentRules().add(rs0Rule);
        RuleSet rs1 = newRuleSet("S3_RS1");
        rs1.getAgentRules().add(rs1Rule);
        controller().getRuleSets().put(3, rs0);
        controller().getRuleSets().put(4, rs1);

        RuleSetFacts f0 = new RuleSetFacts(3);
        f0.put(RULE_TYPE, "RS_ZERO_RULE");
        controller().fire(f0);
        if (rs0Rule.executions != 1 || rs1Rule.executions != 0) {
            throw new IllegalStateException("rule set 0 not isolated");
        }
        System.out.println("JRBA_S3_RS0");

        RuleSetFacts f1 = new RuleSetFacts(4);
        f1.put(RULE_TYPE, "RS_ONE_RULE");
        controller().fire(f1);
        if (rs1Rule.executions != 1 || rs0Rule.executions != 1) {
            throw new IllegalStateException("rule set 1 not isolated");
        }
        System.out.println("JRBA_S3_RS1");
        System.out.println("JRBA_S3_ISOLATED");

        RuleSetFacts ghost = new RuleSetFacts(99);
        ghost.put(RULE_TYPE, "GHOST_RULE");
        controller().fire(ghost);
        System.out.println("JRBA_S3_MISSING_RS_HANDLED");
        System.out.println("JRBA_S3_PASSED");
    }

    // ------------------------------------------------------------------
    // S4 - JADE interop: ACLMessage fact + DF registration/search
    // ------------------------------------------------------------------
    private void runScenario4() {
        System.out.println("JRBA_S4_STARTED");
        MessageRule messageRule = new MessageRule();
        RuleSet ruleSet = newRuleSet("S4_RULE_SET");
        ruleSet.getAgentRules().add(messageRule);
        controller().getRuleSets().put(5, ruleSet);

        ACLMessage msg = new ACLMessage(ACLMessage.INFORM);
        msg.setContent("jrba-payload");
        RuleSetFacts facts = new RuleSetFacts(5);
        facts.put(RULE_TYPE, "JADE_MESSAGE_RULE");
        facts.put("message", msg);
        controller().fire(facts);
        if (!messageRule.executed) {
            throw new IllegalStateException("JADE message rule not executed");
        }
        System.out.println("JRBA_S4_MESSAGE_OK");

        AID df = getDefaultDF();
        YellowPagesRegister.register(this, df, "jrba-service", "jrba-svc-name");
        System.out.println("JRBA_S4_DF_REGISTERED");

        boolean found = false;
        for (int attempt = 0; attempt < 5 && !found; attempt++) {
            found = YellowPagesRegister.search(this, df, "jrba-service").contains(getAID());
            if (!found) {
                try {
                    Thread.sleep(100);
                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                    break;
                }
            }
        }
        if (!found) {
            throw new IllegalStateException("own service not found in DF");
        }
        System.out.println("JRBA_S4_DF_FOUND");

        YellowPagesRegister.deregister(this, df, "jrba-service", "jrba-svc-name");
        System.out.println("JRBA_S4_PASSED");
    }

    // ------------------------------------------------------------------
    // Rule implementations
    // ------------------------------------------------------------------

    @SuppressWarnings("rawtypes")
    private static final class ThresholdRule extends AgentBasicRule {
        private boolean ruleExecuted;

        private ThresholdRule() {
            super((RulesController) null);
        }

        @Override
        public AgentRuleDescription initializeRuleDescription() {
            return new AgentRuleDescription(
                    "FACT_THRESHOLD_RULE", "Facts threshold rule", "Executes when input-value >= 10");
        }

        @Override
        public boolean evaluateRule(RuleSetFacts facts) {
            if (!super.evaluateRule(facts)) {
                return false;
            }
            Object raw = facts.get("input-value");
            return raw instanceof Integer && (Integer) raw >= 10;
        }

        @Override
        public void executeRule(RuleSetFacts facts) {
            ruleExecuted = true;
            facts.put("result", 42);
        }
    }

    @SuppressWarnings("rawtypes")
    private static final class OrderRule extends AgentBasicRule {
        private final String tag;
        private final StringBuilder sink;
        private boolean executed;

        private OrderRule(int priority, String tag, StringBuilder sink) {
            super((RulesController) null, priority);
            this.tag = tag;
            this.sink = sink;
        }

        @Override
        public AgentRuleDescription initializeRuleDescription() {
            return new AgentRuleDescription(
                    "MULTI_ORDER_RULE", "Priority rule " + tag, "Records its execution order");
        }

        @Override
        public void executeRule(RuleSetFacts facts) {
            executed = true;
            sink.append(tag).append(", ");
        }
    }

    @SuppressWarnings("rawtypes")
    private static final class SetScopedRule extends AgentBasicRule {
        private final String type;
        private int executions;

        private SetScopedRule(String type) {
            super((RulesController) null);
            this.type = type;
        }

        @Override
        public AgentRuleDescription initializeRuleDescription() {
            return new AgentRuleDescription(
                    type, "Rule set scoped rule " + type, "Only executes for its owning rule set index");
        }

        @Override
        public String getRuleType() {
            return type;
        }

        @Override
        public boolean evaluateRule(RuleSetFacts facts) {
            return type.equals(facts.get(RULE_TYPE));
        }

        @Override
        public void executeRule(RuleSetFacts facts) {
            executions++;
        }
    }

    @SuppressWarnings("rawtypes")
    private static final class MessageRule extends AgentBasicRule {
        private boolean executed;

        private MessageRule() {
            super((RulesController) null);
        }

        @Override
        public AgentRuleDescription initializeRuleDescription() {
            return new AgentRuleDescription(
                    "JADE_MESSAGE_RULE", "JADE ACLMessage rule", "Validates an ACLMessage carried as a fact");
        }

        @Override
        public boolean evaluateRule(RuleSetFacts facts) {
            if (!super.evaluateRule(facts)) {
                return false;
            }
            Object raw = facts.get("message");
            return raw instanceof ACLMessage && ((ACLMessage) raw).getPerformative() == ACLMessage.INFORM;
        }

        @Override
        public void executeRule(RuleSetFacts facts) {
            ACLMessage msg = (ACLMessage) facts.get("message");
            if (!"jrba-payload".equals(msg.getContent())) {
                throw new IllegalStateException("unexpected message content");
            }
            executed = true;
        }
    }

    private int exitCode;

    @Override
    protected void takeDown() {
        super.takeDown();
        Thread shutdown = new Thread(() -> {
            try {
                Thread.sleep(250);
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
            }
            System.exit(exitCode);
        });
        shutdown.setDaemon(true);
        shutdown.start();
    }
}