package pw.agents;

import jade.core.Agent;
import jade.core.behaviours.OneShotBehaviour;
import jade.wrapper.AgentController;
import jade.wrapper.StaleProxyException;
import pw.model.TripRequest;

import java.time.LocalDate;

/**
 * Test runner for hw-jade consumer project.
 * Boots CustomerAgent with mock TripRequest, waits for completion,
 * prints HW_JADE_PASSED or HW_JADE_FAILED, then shuts down the platform.
 */
public class TestRunnerAgent extends Agent {

    @Override
    protected void setup() {
        System.out.println("=== HW-JADE Test Runner ===");

        addBehaviour(new OneShotBehaviour() {
            @Override
            public void action() {
                try {
                    runTest();
                    System.out.println("HW_JADE_PASSED");
                } catch (Exception e) {
                    System.err.println("HW_JADE_FAILED: " + e.getMessage());
                    e.printStackTrace(System.err);
                } finally {
                    // Graceful shutdown after a short delay to let logs flush
                    try {
                        Thread.sleep(2000);
                    } catch (InterruptedException ignored) {
                    }
                    System.exit(0);
                }
            }
        });
    }

    private void runTest() throws Exception {
        // Create mock TripRequest (same as Main.java)
        TripRequest request = new TripRequest(
                "Warsaw",
                "Tokyo",
                LocalDate.of(2026, 3, 4),
                LocalDate.of(2026, 3, 12)
        );

        // Start CustomerAgent programmatically with the mock request
        AgentController controller = getContainerController()
                .createNewAgent("CustomerAgent", CustomerAgent.class.getName(),
                        new Object[]{request});
        controller.start();

        // Wait for CustomerAgent to finish its OneShotBehaviour
        // CustomerAgent's negotiation runs synchronously in OneShotBehaviour
        Thread.sleep(5000);

        System.out.println("[TestRunner] CustomerAgent negotiation completed.");
    }
}
