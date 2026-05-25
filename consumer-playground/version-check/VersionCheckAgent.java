import jade.core.Agent;
import jade.core.Runtime;

public class VersionCheckAgent extends Agent {
    protected void setup() {
        System.out.println("=== JADE Runtime Verification ===");
        System.out.println("JADE version: " + Runtime.instance().getVersion());
        System.out.println("java.version: " + System.getProperty("java.version"));
        System.out.println("java.vm.version: " + System.getProperty("java.vm.version"));
        System.out.println("RUNTIME_CHECK_PASSED");

        new Thread(() -> {
            try {
                Thread.sleep(3000);
            } catch (InterruptedException e) {
            }
            System.exit(0);
        }).start();
    }
}
