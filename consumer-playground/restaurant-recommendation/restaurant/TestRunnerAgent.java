package restaurant;

import jade.core.Agent;
import jade.core.behaviours.OneShotBehaviour;
import jade.core.AID;
import jade.domain.DFService;
import jade.domain.FIPAAgentManagement.DFAgentDescription;
import jade.domain.FIPAAgentManagement.ServiceDescription;
import jade.domain.FIPAException;
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
                    System.err.println("RESTAURANT_TEST_FAILED");
                    System.exit(1);
                }
            }
        });
    }

    private void runTest() throws Exception {
        // 5 restaurants: Italian x2, Chinese, Japanese, and a "slow" one that never replies to CFP
        Map<String, Double> menu1 = new HashMap<>();
        menu1.put("Pasta", 50.0);
        menu1.put("Pizza", 100.5);
        createAndStart("ItalianRestaurant1", RestaurantAgent.class.getName(),
                new Object[]{"Italian", menu1, new HashMap<String, Object>()});

        Map<String, Double> menu2 = new HashMap<>();
        menu2.put("Pasta", 100.0);
        menu2.put("Ravioli", 80.0);
        Map<String, Object> info2 = new HashMap<>();
        info2.put("smoking", false);
        createAndStart("ItalianRestaurant2", RestaurantAgent.class.getName(),
                new Object[]{"Italian", menu2, info2});

        Map<String, Double> menu3 = new HashMap<>();
        menu3.put("Noodles", 45.0);
        menu3.put("Rice", 30.0);
        createAndStart("ChineseRestaurant", RestaurantAgent.class.getName(),
                new Object[]{"Chinese", menu3, new HashMap<String, Object>()});

        Map<String, Double> menu4 = new HashMap<>();
        menu4.put("Sushi", 55.0);
        menu4.put("Sashimi", 90.0);
        createAndStart("JapaneseRestaurant", RestaurantAgent.class.getName(),
                new Object[]{"Japanese", menu4, new HashMap<String, Object>()});

        Map<String, Double> menu5 = new HashMap<>();
        menu5.put("Sushi", 70.0);
        menu5.put("Sashimi", 95.0);
        createAndStart("SlowRestaurant", RestaurantAgent.class.getName(),
                new Object[]{"Japanese", menu5, new HashMap<String, Object>(), Boolean.FALSE});

        // Delivery + Loyalty (no constructor args)
        Map<String, Double> zoneFees = new HashMap<>();
        zoneFees.put("zoneA", 10.0);
        zoneFees.put("zoneB", 15.0);
        createAndStart("DeliveryAgent", DeliveryAgent.class.getName(), new Object[]{zoneFees});
        createAndStart("LoyaltyAgent", LoyaltyAgent.class.getName(), new Object[0]);

        // Gate: wait until all 5 restaurants are registered in DF
        waitForRestaurants(5);

        createAndStart("BookingAgent", BookingAgent.class.getName(), new Object[0]);
        Thread.sleep(2000);

        sendOrder("O1", "Italian", "Pasta", 75.0, "zoneA");
        sendOrder("O2", "Italian", "Ravioli", 120.0, "zoneB");
        sendOrder("O3", "Italian", "Pizza", 60.0, "zoneA");
        sendOrder("O4", "Japanese", "Sushi", 70.0, "zoneA");

        // Fallback shutdown in case the negotiation coordinator is stuck
        Thread.sleep(30000);
        System.out.println("TEST_RUNNER_FALLBACK_EXIT");
        System.exit(0);
    }

    private void sendOrder(String orderId, String cuisine, String dish, double max, String zone) throws Exception {
        ClientOrder order = new ClientOrder(orderId, cuisine, dish, max, zone, new HashMap<String, Object>());
        ACLMessage req = new ACLMessage(ACLMessage.REQUEST);
        req.addReceiver(new AID("BookingAgent", AID.ISLOCALNAME));
        req.setContentObject(order);
        send(req);
    }

    private void waitForRestaurants(int expected) throws InterruptedException {
        int attempts = 0;
        while (attempts < 50) {
            if (countRestaurants() >= expected) {
                System.out.println("TEST_RUNNER_GATE: " + expected + " restaurants registered");
                return;
            }
            Thread.sleep(200);
            attempts++;
        }
        System.out.println("TEST_RUNNER_GATE: timeout waiting for " + expected + " restaurants");
    }

    private int countRestaurants() {
        DFAgentDescription template = new DFAgentDescription();
        ServiceDescription sd = new ServiceDescription();
        sd.setType("RESTAURANT");
        template.addServices(sd);
        try {
            return DFService.search(this, template).length;
        } catch (FIPAException e) {
            return 0;
        }
    }

    private void createAndStart(String name, String className, Object[] args) throws Exception {
        AgentController c = getContainerController().createNewAgent(name, className, args);
        c.start();
    }
}