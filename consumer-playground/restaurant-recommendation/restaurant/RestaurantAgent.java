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

    @Override
    protected void setup() {
        Object[] args = getArguments();
        this.cuisine = (String) args[0];
        this.menu = (Map<String, Double>) args[1];
        this.additionalInfo = (Map<String, Object>) args[2];

        registerInDF();
        System.out.println("RESTAURANT_DF: " + getLocalName() + " registered with cuisine=" + cuisine);

        addBehaviour(new HandleCFPBehaviour());
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
            System.err.println("DF registration failed: " + e.getMessage());
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
                if (!cuisine.equalsIgnoreCase(order.getCuisine())) {
                    sendRefuse(msg);
                    return;
                }
                Double price = menu.get(order.getDish());
                if (price == null || price > order.getMaxPrice()) {
                    sendRefuse(msg);
                    return;
                }

                RestaurantData data = new RestaurantData(getLocalName(), menu, additionalInfo);
                ACLMessage reply = msg.createReply();
                reply.setPerformative(ACLMessage.PROPOSE);
                reply.setContentObject(data);
                send(reply);
                System.out.println("RESTAURANT_PROPOSAL: " + getLocalName()
                        + " -> " + order.getDish() + "=" + price);
            } catch (Exception e) {
                sendRefuse(msg);
            }
        }

        private void sendRefuse(ACLMessage msg) {
            ACLMessage reply = msg.createReply();
            reply.setPerformative(ACLMessage.REFUSE);
            send(reply);
        }
    }
}
