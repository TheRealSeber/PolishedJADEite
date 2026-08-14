package org.jrba.consumer;

import jade.core.behaviours.OneShotBehaviour;
import org.jrba.agentmodel.domain.AbstractAgent;

/** Minimal runtime probe for the JRBA-to-JADE integration boundary. */
public final class JrbaIntegrationAgent extends AbstractAgent {

    @Override
    protected void setup() {
        addBehaviour(new OneShotBehaviour() {
            @Override
            public void action() {
                int exitCode = 0;
                System.out.println("JRBA_TEST_STARTED");
                try {
                    if (getObjectsNumber() != 0 || !"DEFAULT_RULE_SET".equals(getDefaultRuleSet())) {
                        throw new IllegalStateException("Unexpected JRBA defaults");
                    }
                    System.out.println("JRBA_TEST_PASSED");
                } catch (Throwable failure) {
                    exitCode = 1;
                    System.out.println("JRBA_TEST_FAILED: " + failure.getMessage());
                } finally {
                    System.exit(exitCode);
                }
            }
        });
    }
}
