package pw.agents;

import jade.core.Agent;
import jade.core.behaviours.CyclicBehaviour;
import jade.lang.acl.ACLMessage;
import pw.model.FlightProposal;
import pw.model.FlightRoute;
import pw.model.TripRequest;

import java.util.Comparator;
import java.util.List;
import java.util.Optional;

public class FlightAgent extends Agent {
    private List<FlightRoute> catalog;

    @Override
    @SuppressWarnings("unchecked")
    protected void setup() {
        Object[] args = getArguments();
        this.catalog = (List<FlightRoute>) args[0];
        String connectedAgency = (String) args[1];
        ConversationLog.event(this, "Initialized flight catalog entries=" + catalog.size() + ", owner=" + connectedAgency);

        DfUtils.registerService(this, "flight-provider", getLocalName() + "-flight", connectedAgency);

        addBehaviour(new CyclicBehaviour() {
            @Override
            public void action() {
                ACLMessage cfp = receive();
                if (cfp == null) {
                    block();
                    return;
                }
                if (cfp.getPerformative() != ACLMessage.CFP) {
                    return;
                }
                ConversationLog.received(FlightAgent.this, cfp, "flight quote request");

                ACLMessage reply = cfp.createReply();
                try {
                    TripRequest req = (TripRequest) cfp.getContentObject();
                    FlightProposal proposal = bestRoundTrip(req);
                    if (proposal == null) {
                        reply.setPerformative(ACLMessage.REFUSE);
                        reply.setContent("No round-trip found");
                    } else {
                        reply.setPerformative(ACLMessage.PROPOSE);
                        reply.setContentObject(proposal);
                    }
                } catch (Exception e) {
                    reply.setPerformative(ACLMessage.FAILURE);
                    reply.setContent("FlightAgent error: " + e.getMessage());
                }
                send(reply);
                ConversationLog.sent(FlightAgent.this, reply, "flight quote response");
            }
        });
    }

    private FlightProposal bestRoundTrip(TripRequest req) {
        // START GENAI
        Optional<FlightRoute> outbound = catalog.stream()
                .filter(f -> f.fromCity().equalsIgnoreCase(req.fromCity()))
                .filter(f -> f.toCity().equalsIgnoreCase(req.toCity()))
                .filter(f -> f.date().equals(req.departDate()))
                .min(Comparator.comparingInt(FlightRoute::priceEur));

        Optional<FlightRoute> inbound = catalog.stream()
                .filter(f -> f.fromCity().equalsIgnoreCase(req.toCity()))
                .filter(f -> f.toCity().equalsIgnoreCase(req.fromCity()))
                .filter(f -> f.date().equals(req.returnDate()))
                .min(Comparator.comparingInt(FlightRoute::priceEur));
        // END GENAI

        if (outbound.isEmpty() || inbound.isEmpty()) {
            return null;
        }

        int totalPrice = outbound.get().priceEur() + inbound.get().priceEur();
        return new FlightProposal(getLocalName(), totalPrice);
    }
}