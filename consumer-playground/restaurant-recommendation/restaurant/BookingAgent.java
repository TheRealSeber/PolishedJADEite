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

import java.util.Enumeration;
import java.util.Vector;

public class BookingAgent extends Agent {
    private ClientOrder currentOrder;

    @Override
    protected void setup() {
        System.out.println("BOOKING_AGENT: " + getLocalName() + " is ready");
        addBehaviour(new WaitForOrderBehaviour());
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
                currentOrder = (ClientOrder) msg.getContentObject();
                System.out.println("BOOKING_ORDER: received " + currentOrder.getDish()
                        + " max=" + currentOrder.getMaxPrice());

                AID[] restaurants = searchRestaurants();
                System.out.println("BOOKING_DF_FOUND: " + restaurants.length + " restaurants");

                if (restaurants.length == 0) {
                    System.out.println("BOOKING_NO_RESTAURANTS_FOUND");
                    return;
                }

                ACLMessage cfp = new ACLMessage(ACLMessage.CFP);
                for (AID restaurant : restaurants) {
                    cfp.addReceiver(restaurant);
                }
                cfp.setProtocol("NEW_CLIENT_ORDER_PROTOCOL");
                cfp.setContentObject(currentOrder);
                cfp.setReplyByDate(new java.util.Date(System.currentTimeMillis() + 10000));

                myAgent.addBehaviour(new ContractNetHandler(myAgent, cfp));
            } catch (Exception e) {
                System.err.println("BOOKING_ERROR: " + e.getMessage());
                e.printStackTrace(System.err);
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
            System.err.println("DF search failed: " + e.getMessage());
            return new AID[0];
        }
    }

    private class ContractNetHandler extends ContractNetInitiator {
        public ContractNetHandler(Agent a, ACLMessage cfp) {
            super(a, cfp);
        }

        @Override
        protected void handlePropose(ACLMessage propose, Vector acceptances) {
            try {
                RestaurantData data = (RestaurantData) propose.getContentObject();
                Double price = data.getMenu().get(currentOrder.getDish());
                System.out.println("BOOKING_PROPOSAL: from " + propose.getSender().getLocalName()
                        + " " + currentOrder.getDish() + "=" + price);
            } catch (Exception e) {
            }
        }

        @Override
        protected void handleRefuse(ACLMessage refuse) {
            System.out.println("BOOKING_REFUSE: from " + refuse.getSender().getLocalName());
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
                        Double price = data.getMenu().get(currentOrder.getDish());
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
                System.out.println("BOOKING_SELECT: " + bestOffer.getName()
                        + " " + currentOrder.getDish() + "=" + bestPrice);
                System.out.println("RESTAURANT_TEST_PASSED");
                new Thread(() -> {
                    try {
                        Thread.sleep(3000);
                    } catch (InterruptedException e) {
                    }
                    System.exit(0);
                }).start();
            } else {
                System.out.println("BOOKING_NO_VIABLE_OFFERS");
                System.out.println("RESTAURANT_TEST_FAILED");
            }
        }
    }
}
