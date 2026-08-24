package restaurant;

import jade.core.Agent;
import jade.lang.acl.ACLMessage;
import jade.lang.acl.MessageTemplate;
import jade.proto.AchieveREResponder;

public class LoyaltyAgent extends Agent {

    @Override
    protected void setup() {
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
                    int points = (int) (result.getPrice() / 10.0);
                    inform.setContent("LOYALTY_POINTS " + result.getOrderId() + " " + points);
                    System.out.println("LOYALTY_POINTS: " + result.getOrderId() + " " + points);
                } catch (Exception e) {
                    inform.setPerformative(ACLMessage.FAILURE);
                }
                return inform;
            }
        });
    }
}