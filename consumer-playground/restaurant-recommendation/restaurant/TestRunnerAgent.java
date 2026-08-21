package restaurant;

import jade.core.Agent;
import jade.core.behaviours.OneShotBehaviour;
import jade.lang.acl.ACLMessage;
import jade.wrapper.AgentController;

import java.util.HashMap;
import java.util.Map;

public class TestRunnerAgent extends Agent {

    @Override
    protected void setup() {
        System.out.println("=== Restaurant Recommendation Test Runner ===");

        addBehaviour(new OneShotBehaviour() {
            @Override
            public void action() {
                try {
                    runTest();
                } catch (Exception e) {
                    System.err.println("RESTAURANT_TEST_FAILED: " + e.getMessage());
                    e.printStackTrace(System.err);
                    System.exit(1);
                }
            }
        });
    }

    private void runTest() throws Exception {
        Map<String, Double> menu1 = new HashMap<>();
        menu1.put("Pasta", 50.0);
        menu1.put("Pizza", 100.5);
        Map<String, Object> info1 = new HashMap<>();
        createAndStart("ItalianRestaurant1", RestaurantAgent.class.getName(),
                new Object[]{"Italian", menu1, info1});

        Map<String, Double> menu2 = new HashMap<>();
        menu2.put("Pasta", 100.0);
        menu2.put("Pizza", 100.5);
        Map<String, Object> info2 = new HashMap<>();
        info2.put("smoking", false);
        info2.put("dog_friendly", true);
        createAndStart("ItalianRestaurant2", RestaurantAgent.class.getName(),
                new Object[]{"Italian", menu2, info2});

        createAndStart("BookingAgent", BookingAgent.class.getName(), new Object[0]);

        Thread.sleep(3000);

        Map<String, Object> instructions = new HashMap<>();
        ClientOrder order = new ClientOrder("Italian", "Pasta", 75.0, instructions);

        ACLMessage req = new ACLMessage(ACLMessage.REQUEST);
        req.addReceiver(new jade.core.AID("BookingAgent", jade.core.AID.ISLOCALNAME));
        req.setContentObject(order);
        send(req);

        System.out.println("TEST_ORDER_SENT: Italian Pasta, max 75.0");
    }

    private void createAndStart(String name, String className, Object[] args) throws Exception {
        AgentController c = getContainerController().createNewAgent(name, className, args);
        c.start();
    }
}
