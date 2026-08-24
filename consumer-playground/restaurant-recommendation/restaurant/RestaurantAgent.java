package restaurant;

import jade.core.Agent;
import jade.domain.DFService;
import jade.domain.FIPAAgentManagement.DFAgentDescription;
import jade.domain.FIPAAgentManagement.ServiceDescription;
import jade.domain.FIPAException;
import jade.lang.acl.ACLMessage;
import jade.lang.acl.MessageTemplate;
import jade.core.behaviours.CyclicBehaviour;
import jade.core.AID;

import java.util.Map;

public class RestaurantAgent extends Agent {
    private String cuisine;
    private Map<String, Double> menu;
    private Map<String, Object> additionalInfo;
    private boolean respondsToCfp = true;

    @Override
    protected void setup() {
        Object[] args = getArguments();
        this.cuisine = (String) args[0];
        this.menu = (Map<String, Double>) args[1];
        this.additionalInfo = (Map<String, Object>) args[2];
        if (args.length > 3) {
            this.respondsToCfp = Boolean.TRUE.equals(args[3]);
        }

        registerInDF();
        System.out.println("RESTAURANT_DF: " + getLocalName() + " registered with cuisine=" + cuisine);

        if (respondsToCfp) {
            addBehaviour(new HandleCFPBehaviour());
        }
    }

    private void registerInDF() {
        DFAgentDescription dfd = new DFAgentDescription();
        dfd.setName(getAID());
        ServiceDescription sd = new ServiceDescription();
        sd.setType("RESTAURANT");
        sd.setName(getLocalName());
        dfd.addServices(sd);
        try {
            DFService.register(this, dfd);
        } catch (FIPAException e) {
            System.err.println("DF_REGISTRATION_FAILED");
        }
    }

    @Override
    protected void takeDown() {
        try {
            DFService.deregister(this);
        } catch (FIPAException e) {
        }
    }

    private class HandleCFPBehaviour extends CyclicBehaviour {
        @Override
        public void action() {
            ACLMessage msg = receive(MessageTemplate.and(
                    MessageTemplate.MatchPerformative(ACLMessage.CFP),
                    MessageTemplate.MatchProtocol("NEW_CLIENT_ORDER_PROTOCOL")
            ));
            if (msg == null) {
                block();
                return;
            }

            try {
                ClientOrder order = (ClientOrder) msg.getContentObject();
                String reason = null;
                if (!cuisine.equalsIgnoreCase(order.getCuisine())) {
                    reason = "wrongCuisine";
                } else {
                    Double price = menu.get(order.getDish());
                    if (price == null) {
                        reason = "dishUnavailable";
                    } else if (price > order.getMaxPrice()) {
                        reason = "overBudget";
                    }
                }
                if (reason != null) {
                    sendRefuse(msg, order, reason);
                    return;
                }

                Double price = menu.get(order.getDish());
                RestaurantData data = new RestaurantData(getLocalName(), menu, additionalInfo);
                ACLMessage reply = msg.createReply();
                reply.setPerformative(ACLMessage.PROPOSE);
                reply.setContentObject(data);
                send(reply);
                System.out.println("RESTAURANT_PROPOSAL: " + getLocalName()
                        + " -> " + order.getDish() + "=" + price);
            } catch (Exception e) {
                sendRefuse(msg, null, "malformed");
            }
        }

        private void sendRefuse(ACLMessage msg, ClientOrder order, String reason) {
            ACLMessage reply = msg.createReply();
            reply.setPerformative(ACLMessage.REFUSE);
            send(reply);
            String orderTag = order != null ? order.getOrderId() : "UNKNOWN";
            System.out.println("BOOKING_REFUSE: " + orderTag + " " + reason + " from " + getLocalName());
        }
    }
}