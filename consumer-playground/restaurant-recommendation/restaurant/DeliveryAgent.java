package restaurant;

import jade.core.Agent;
import jade.domain.DFService;
import jade.domain.FIPAAgentManagement.DFAgentDescription;
import jade.domain.FIPAAgentManagement.ServiceDescription;
import jade.lang.acl.ACLMessage;
import jade.lang.acl.MessageTemplate;
import jade.proto.AchieveREResponder;
import jade.proto.SubscriptionInitiator;

import java.util.HashMap;
import java.util.Map;

public class DeliveryAgent extends Agent {
    private Map<String, Double> zoneFees = new HashMap<String, Double>();

    @Override
    protected void setup() {
        Object[] args = getArguments();
        if (args != null && args.length > 0 && args[0] instanceof Map) {
            @SuppressWarnings("unchecked")
            Map<String, Double> fees = (Map<String, Double>) args[0];
            zoneFees.putAll(fees);
        }

        subscribeToDF();

        addBehaviour(new AchieveREResponder(this, MessageTemplate.MatchPerformative(ACLMessage.REQUEST)) {
            @Override
            protected ACLMessage prepareResponse(ACLMessage request) {
                return null;
            }

            @Override
            protected ACLMessage prepareResultNotification(ACLMessage request, ACLMessage response) {
                ACLMessage inform = request.createReply();
                inform.setPerformative(ACLMessage.INFORM);
                try {
                    BookingResult result = (BookingResult) request.getContentObject();
                    Double fee = zoneFees.get(result.getDeliveryZone());
                    if (fee == null) {
                        fee = 0.0;
                    }
                    inform.setContent("DELIVERY_QUOTE " + result.getOrderId() + " " + fee);
                    System.out.println("DELIVERY_QUOTE: " + result.getOrderId() + " fee=" + fee);
                } catch (Exception e) {
                    inform.setPerformative(ACLMessage.FAILURE);
                }
                return inform;
            }
        });
    }

    private void subscribeToDF() {
        DFAgentDescription template = new DFAgentDescription();
        ServiceDescription sd = new ServiceDescription();
        sd.setType("RESTAURANT");
        template.addServices(sd);
        ACLMessage sub = DFService.createSubscriptionMessage(this, getDefaultDF(), template, null);
        addBehaviour(new SubscriptionInitiator(this, sub) {
            @Override
            protected void handleInform(ACLMessage inform) {
            }
        });
        System.out.println("DELIVERY_DF_SUBSCRIBE: active");
    }
}