package org.jrba.consumer;

import jade.core.behaviours.OneShotBehaviour;
import jade.core.behaviours.Behaviour;
import java.util.List;
import org.jrba.agentmodel.behaviour.ListenForControllerObjects;
import org.jrba.agentmodel.domain.AbstractAgent;
import org.jrba.rulesengine.RulesController;
import org.jrba.rulesengine.rest.domain.RuleSetRest;
import org.jrba.rulesengine.ruleset.RuleSet;
import org.jrba.rulesengine.ruleset.RuleSetFacts;

/** Minimal runtime probe for the JRBA-to-JADE integration boundary. */
public final class JrbaIntegrationAgent extends AbstractAgent {

    @Override
    protected void setup() {
        super.setup();
    }

    @Override
    protected List<Behaviour> prepareStartingBehaviours() {
        return List.of(new OneShotBehaviour() {
            @Override
            public void action() {
                System.out.println("JRBA_TEST_STARTED");
                try {
                    RuleSetRest emptyRuleSet = new RuleSetRest();
                    emptyRuleSet.setName("JRBA_EMPTY_RULE_SET");
                    emptyRuleSet.setRules(List.of());
                    RulesController<?, ?> rulesController = new RulesController<>();
                    rulesController.getRuleSets().put(0, new RuleSet(emptyRuleSet));
                    rulesController.fire(new RuleSetFacts(0));
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
