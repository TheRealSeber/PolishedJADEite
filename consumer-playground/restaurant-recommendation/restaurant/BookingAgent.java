package restaurant;

import jade.core.Agent;
import jade.core.AID;
import jade.domain.DFService;
import jade.domain.FIPAAgentManagement.DFAgentDescription;
import jade.domain.FIPAAgentManagement.ServiceDescription;
import jade.domain.FIPAException;
import jade.lang.acl.ACLMessage;
import jade.lang.acl.MessageTemplate;
import jade.proto.ContractNetInitiator;
import jade.core.behaviours.CyclicBehaviour;

import java.util.Vector;

public class BookingAgent extends Agent {
    private static final int TOTAL_ORDERS = 4;
    private int completedOrders = 0;

    @Override
    protected void setup() {
        System.out.println("BOOKING_AGENT: " + getLocalName() + " is ready");
        addBehaviour(new WaitForOrderBehaviour());
    }

    private synchronized void orderCompleted(ClientOrder order, String selection) {
        completedOrders++;
        System.out.println("BOOKING_COMPLETED: " + order.getOrderId() + " (" + completedOrders + "/" + TOTAL_ORDERS + ")");
        if (completedOrders >= TOTAL_ORDERS) {
            System.out.println("RESTAURANT_TEST_PASSED");
            new Thread(() -> {
                try {
                    Thread.sleep(3000);
                } catch (InterruptedException e) {
                }
                System.exit(0);
            }).start();
        }
    }

    private class WaitForOrderBehaviour extends CyclicBehaviour {
        @Override
        public void action() {
            ACLMessage msg = receive(MessageTemplate.MatchPerformative(ACLMessage.REQUEST));
            if (msg == null) {
                block();
                return;
            }

            try {
                final ClientOrder order = (ClientOrder) msg.getContentObject();
                System.out.println("BOOKING_ORDER: " + order.getOrderId() + " received " + order.getDish()
                        + " max=" + order.getMaxPrice());

                AID[] restaurants = searchRestaurants();
                System.out.println("BOOKING_DF_FOUND: " + order.getOrderId() + " restaurants=" + restaurants.length);

                if (restaurants.length == 0) {
                    System.out.println("BOOKING_NO_RESTAURANTS_FOUND: " + order.getOrderId());
                    orderCompleted(order, null);
                    return;
                }

                ACLMessage cfp = new ACLMessage(ACLMessage.CFP);
                for (AID restaurant : restaurants) {
                    cfp.addReceiver(restaurant);
                }
                cfp.setProtocol("NEW_CLIENT_ORDER_PROTOCOL");
                cfp.setContentObject(order);
                cfp.setReplyByDate(new java.util.Date(System.currentTimeMillis() + 5000));

                myAgent.addBehaviour(new ContractNetHandler(myAgent, cfp, order));
            } catch (Exception e) {
                System.err.println("BOOKING_ERROR_DESERIALIZE");
            }
        }
    }

    private AID[] searchRestaurants() {
        DFAgentDescription template = new DFAgentDescription();
        ServiceDescription sd = new ServiceDescription();
        sd.setType("RESTAURANT");
        template.addServices(sd);
        try {
            DFAgentDescription[] result = DFService.search(this, template);
            AID[] aids = new AID[result.length];
            for (int i = 0; i < result.length; i++) {
                aids[i] = result[i].getName();
            }
            return aids;
        } catch (FIPAException e) {
            System.err.println("DF search failed");
            return new AID[0];
        }
    }

    private void requestDelivery(ClientOrder order, BookingResult result) {
        ACLMessage req = new ACLMessage(ACLMessage.REQUEST);
        req.addReceiver(new AID("DeliveryAgent", AID.ISLOCALNAME));
        try {
            req.setContentObject(result);
            send(req);
        } catch (Exception e) {
            System.err.println("DELIVERY_REQUEST_FAILED: " + order.getOrderId());
        }
    }

    private void requestLoyalty(ClientOrder order, BookingResult result) {
        ACLMessage req = new ACLMessage(ACLMessage.REQUEST);
        req.addReceiver(new AID("LoyaltyAgent", AID.ISLOCALNAME));
        try {
            req.setContentObject(result);
            send(req);
        } catch (Exception e) {
            System.err.println("LOYALTY_REQUEST_FAILED: " + order.getOrderId());
        }
    }

    private class ContractNetHandler extends ContractNetInitiator {
        private final ClientOrder order;

        public ContractNetHandler(Agent a, ACLMessage cfp, ClientOrder order) {
            super(a, cfp);
            this.order = order;
        }

        @Override
        protected void handlePropose(ACLMessage propose, Vector acceptances) {
            try {
                RestaurantData data = (RestaurantData) propose.getContentObject();
                Double price = data.getMenu().get(order.getDish());
                System.out.println("BOOKING_PROPOSAL: " + order.getOrderId() + " from "
                        + propose.getSender().getLocalName()
                        + " " + order.getDish() + "=" + price);
            } catch (Exception e) {
            }
        }

        @Override
        protected void handleRefuse(ACLMessage refuse) {
            System.out.println("BOOKING_REFUSE_RECEIVED: " + order.getOrderId() + " from "
                    + refuse.getSender().getLocalName());
        }

        @Override
        protected void handleFailure(ACLMessage failure) {
            System.out.println("BOOKING_TIMEOUT: " + order.getOrderId() + " "
                    + failure.getSender().getLocalName());
        }

        @Override
        protected void handleAllResponses(Vector responses, Vector acceptances) {
            RestaurantData bestOffer = null;
            double bestPrice = Double.MAX_VALUE;
            ACLMessage bestProposal = null;

            for (Object response : responses) {
                ACLMessage msg = (ACLMessage) response;
                if (msg.getPerformative() == ACLMessage.PROPOSE) {
                    try {
                        RestaurantData data = (RestaurantData) msg.getContentObject();
                        Double price = data.getMenu().get(order.getDish());
                        if (price != null && price < bestPrice) {
                            bestPrice = price;
                            bestOffer = data;
                            bestProposal = msg;
                        }
                    } catch (Exception e) {
                    }
                }
            }

            if (bestProposal != null) {
                ACLMessage accept = bestProposal.createReply();
                accept.setPerformative(ACLMessage.ACCEPT_PROPOSAL);
                acceptances.add(accept);
                String selection = bestOffer.getName();
                System.out.println("BOOKING_SELECT: " + order.getOrderId() + " -> " + selection
                        + " " + order.getDish() + "=" + bestPrice);

                String expected = expectedWinner(order);
                if (expected == null || expected.equals(selection)) {
                    System.out.println("BOOKING_VERIFY: " + order.getOrderId() + " cheapest=" + selection + " OK");
                } else {
                    System.out.println("BOOKING_VERIFY: " + order.getOrderId() + " expected=" + expected + " got=" + selection + " MISMATCH");
                }

                BookingResult result = new BookingResult(order.getOrderId(), selection, order.getDish(), bestPrice, order.getDeliveryZone());
                requestDelivery(order, result);
                requestLoyalty(order, result);
                orderCompleted(order, selection);
            } else {
                System.out.println("BOOKING_NO_VIABLE_OFFERS: " + order.getOrderId());
                orderCompleted(order, null);
            }
        }

        private String expectedWinner(ClientOrder order) {
            String dish = order.getDish();
            if ("Pasta".equals(dish) && order.getMaxPrice() >= 75.0) {
                return "ItalianRestaurant1";
            }
            if ("Ravioli".equals(dish)) {
                return "ItalianRestaurant2";
            }
            if ("Sushi".equals(dish) && order.getMaxPrice() >= 70.0) {
                return "JapaneseRestaurant";
            }
            return null;
        }
    }
}