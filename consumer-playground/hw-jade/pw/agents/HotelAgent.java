package pw.agents;

import jade.core.Agent;
import jade.core.behaviours.CyclicBehaviour;
import jade.lang.acl.ACLMessage;
import pw.model.HotelProposal;
import pw.model.HotelStay;
import pw.model.TripRequest;

import java.time.LocalDate;
import java.util.Comparator;
import java.util.List;

public class HotelAgent extends Agent {
    private List<HotelStay> catalog;

    @Override
    @SuppressWarnings("unchecked")
    protected void setup() {
        Object[] args = getArguments();
        this.catalog = (List<HotelStay>) args[0];
        String connectedAgency = (String) args[1];
        ConversationLog.event(this, "Initialized hotel catalog entries=" + catalog.size() + ", owner=" + connectedAgency);

        DfUtils.registerService(this, "hotel-provider", getLocalName() + "-hotel", connectedAgency);

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
                ConversationLog.received(HotelAgent.this, cfp, "hotel quote request");

                ACLMessage reply = cfp.createReply();
                try {
                    TripRequest req = (TripRequest) cfp.getContentObject();
                    HotelProposal proposal = bestMatchingHotel(req);
                    if (proposal == null) {
                        reply.setPerformative(ACLMessage.REFUSE);
                        reply.setContent("No matching hotel stay");
                    } else {
                        reply.setPerformative(ACLMessage.PROPOSE);
                        reply.setContentObject(proposal);
                    }
                } catch (Exception e) {
                    reply.setPerformative(ACLMessage.FAILURE);
                    reply.setContent("HotelAgent error: " + e.getMessage());
                }
                send(reply);
                ConversationLog.sent(HotelAgent.this, reply, "hotel quote response");
            }
        });
    }

    private HotelProposal bestMatchingHotel(TripRequest req) {
        LocalDate requestedFrom = req.departDate();
        LocalDate requestedTo = req.returnDate();

        // START GENAI
        return catalog.stream()
                .filter(stay -> stay.city().equalsIgnoreCase(req.toCity()))
                .filter(stay -> !stay.fromDate().isAfter(requestedFrom) && !stay.toDate().isBefore(requestedTo))
                .min(Comparator.comparingInt(HotelStay::priceEur))
                .map(stay -> new HotelProposal(getLocalName(), stay.priceEur()))
                .orElse(null);
        // END GENAI
    }
}