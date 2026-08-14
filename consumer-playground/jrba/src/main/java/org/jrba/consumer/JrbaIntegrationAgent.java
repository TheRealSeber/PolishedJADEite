package org.jrba.consumer;

import jade.core.behaviours.OneShotBehaviour;
import jade.core.behaviours.Behaviour;
import java.util.List;
import org.jrba.agentmodel.domain.AbstractAgent;

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
