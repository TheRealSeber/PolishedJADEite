package pw.agents;

import jade.core.AID;
import jade.core.Agent;
import jade.core.behaviours.OneShotBehaviour;
import jade.domain.FIPAAgentManagement.DFAgentDescription;
import jade.lang.acl.ACLMessage;
import jade.lang.acl.MessageTemplate;
import pw.model.AgencyOffer;
import pw.model.Payment;
import pw.model.TripRequest;

import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

public class CustomerAgent extends Agent {
    private TripRequest request;

    @Override
    protected void setup() {
        Object[] args = getArguments();
        this.request = (TripRequest) args[0];
        ConversationLog.event(this, "Customer initialized for request " + request.fromCity() + " -> " + request.toCity());

        addBehaviour(new OneShotBehaviour() {
            @Override
            public void action() {
                runNegotiation();
            }
        });
    }

    private void runNegotiation() {
        List<DFAgentDescription> agencies = DfUtils.searchByType(this, "travel-agency");
        ConversationLog.event(this, "Found agencies in DF: " + agencies.size());
        if (agencies.isEmpty()) {
            System.out.println("No travel agencies found in DF.");
            return;
        }

        String conversationId = "trip-" + UUID.randomUUID();

        // Task 2.a: customer sends trip requirements to all travel agencies.
        ACLMessage cfp = new ACLMessage(ACLMessage.CFP);
        for (DFAgentDescription agency : agencies) {
            cfp.addReceiver(agency.getName());
        }
        cfp.setConversationId(conversationId);
        try {
            cfp.setContentObject(request);
        } catch (Exception e) {
            System.out.println("Cannot serialize trip request: " + e.getMessage());
            return;
        }
        send(cfp);
        ConversationLog.sent(this, cfp, "trip request broadcast");

        List<ACLMessage> proposals = new ArrayList<>();
        for (int i = 0; i < agencies.size(); i++) {
            ACLMessage reply = blockingReceive(
                    MessageTemplate.MatchConversationId(conversationId),
                    8_000
            );
            if (reply != null) {
                ConversationLog.received(this, reply, "agency offer response");
            }
            if (reply != null && reply.getPerformative() == ACLMessage.PROPOSE) {
                proposals.add(reply);
            }
        }

        if (proposals.isEmpty()) {
            System.out.println("No agency could provide a complete offer.");
            return;
        }

        ACLMessage winnerMsg = null;
        AgencyOffer winnerOffer = null;
        for (ACLMessage proposal : proposals) {
            try {
                AgencyOffer offer = (AgencyOffer) proposal.getContentObject();
                if (winnerOffer == null || offer.totalPriceEur() < winnerOffer.totalPriceEur()) {
                    winnerOffer = offer;
                    winnerMsg = proposal;
                }
            } catch (Exception ignored) {
            }
        }

        if (winnerMsg == null || winnerOffer == null) {
            System.out.println("Could not parse agency offers.");
            return;
        }

        for (ACLMessage proposal : proposals) {
            ACLMessage decision = proposal.createReply();
            if (proposal == winnerMsg) {
                decision.setPerformative(ACLMessage.ACCEPT_PROPOSAL);
            } else {
                decision.setPerformative(ACLMessage.REJECT_PROPOSAL);
            }
            decision.setConversationId(conversationId);
            send(decision);
            ConversationLog.sent(this, decision, proposal == winnerMsg ? "selected winner" : "rejected offer");
        }

        System.out.println("Selected " + winnerOffer.agencyName() + " with total " + winnerOffer.totalPriceEur() + " EUR");

        ACLMessage payment = new ACLMessage(ACLMessage.INFORM);
        payment.addReceiver(new AID(winnerOffer.agencyName(), AID.ISLOCALNAME));
        payment.setConversationId(conversationId + "-payment");
        try {
            payment.setContentObject(new Payment(winnerOffer.totalPriceEur()));
        } catch (Exception e) {
            System.out.println("Cannot serialize payment: " + e.getMessage());
            return;
        }
        send(payment);
        ConversationLog.sent(this, payment, "payment sent to winning agency");

        ACLMessage confirmation = blockingReceive(
                MessageTemplate.MatchConversationId(conversationId + "-payment"),
                10_000
        );
        if (confirmation != null) {
            ConversationLog.received(this, confirmation, "booking confirmation");
        }
        if (confirmation == null) {
            System.out.println("No booking confirmation received.");
            return;
        }

        if (confirmation.getPerformative() == ACLMessage.INFORM) {
            System.out.println("SUCCESS: " + confirmation.getContent());
        } else {
            System.out.println("FAILURE: " + confirmation.getContent());
        }
    }
}