package org.jrba.consumer;

import static org.jrba.rulesengine.constants.FactTypeConstants.RULE_TYPE;

import jade.core.behaviours.OneShotBehaviour;
import jade.core.behaviours.Behaviour;
import java.util.List;
import org.jrba.agentmodel.behaviour.ListenForControllerObjects;
import org.jrba.agentmodel.domain.AbstractAgent;
import org.jrba.rulesengine.RulesController;
import org.jrba.rulesengine.rule.AgentBasicRule;
import org.jrba.rulesengine.rule.AgentRuleDescription;
import org.jrba.rulesengine.rest.domain.RuleSetRest;
import org.jrba.rulesengine.ruleset.RuleSet;
import org.jrba.rulesengine.ruleset.RuleSetFacts;

/** Minimal runtime probe for the JRBA-to-JADE integration boundary. */
public final class JrbaIntegrationAgent extends AbstractAgent {

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
                    SmokeRule smokeRule = new SmokeRule();
                    RuleSetRest emptyRuleSet = new RuleSetRest();
                    emptyRuleSet.setName("JRBA_EMPTY_RULE_SET");
                    emptyRuleSet.setRules(List.of());
                    RuleSet ruleSet = new RuleSet(emptyRuleSet);
                    ruleSet.getAgentRules().add(smokeRule);
                    RulesController<?, ?> rulesController = getRulesController();
                    rulesController.getRuleSets().put(0, ruleSet);
                    RuleSetFacts facts = new RuleSetFacts(0);
                    facts.put(RULE_TYPE, "JRBA_SMOKE_RULE");
                    rulesController.fire(facts);
                    if (!smokeRule.ruleExecuted) {
                        throw new IllegalStateException("JRBA smoke rule did not execute");
                    }
                    System.out.println("JRBA_BEHAVIOR_EXECUTED");
                    if (getObjectsNumber() != 0 || !"DEFAULT_RULE_SET".equals(getDefaultRuleSet())) {
                        throw new IllegalStateException("Unexpected JRBA defaults");
                    }
                    System.out.println("JRBA_TEST_PASSED");
                } catch (Throwable failure) {
                    exitCode = 1;
                    System.out.println("JRBA_TEST_FAILED: " + failure.getMessage());
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

    private static final class SmokeRule extends AgentBasicRule {
        private boolean ruleExecuted;

        private SmokeRule() {
            super((RulesController) null);
        }

        @Override
        public AgentRuleDescription initializeRuleDescription() {
            return new AgentRuleDescription(
                    "JRBA_SMOKE_RULE", "JRBA smoke rule", "In-memory JRBA smoke rule");
        }

        @Override
        public boolean evaluateRule(RuleSetFacts facts) {
            return "JRBA_SMOKE_RULE".equals(facts.get(RULE_TYPE));
        }

        @Override
        public void executeRule(RuleSetFacts facts) {
            ruleExecuted = true;
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
