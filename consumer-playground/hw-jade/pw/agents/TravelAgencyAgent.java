package pw.agents;

import jade.core.AID;
import jade.core.Agent;
import jade.core.behaviours.CyclicBehaviour;
import jade.domain.FIPAAgentManagement.DFAgentDescription;
import jade.domain.FIPAAgentManagement.ServiceDescription;
import jade.lang.acl.ACLMessage;
import jade.lang.acl.MessageTemplate;
import pw.model.AgencyOffer;
import pw.model.FlightProposal;
import pw.model.HotelProposal;
import pw.model.Payment;
import pw.model.TripRequest;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

public class TravelAgencyAgent extends Agent {
    private int serviceFeeEur;
    private Set<String> allowedHotelProviders;
    private Set<String> allowedFlightProviders;

    @Override
    @SuppressWarnings("unchecked")
    protected void setup() {
        Object[] args = getArguments();
        this.serviceFeeEur = (Integer) args[0];
        this.allowedHotelProviders = new HashSet<>(((List<String>) args[1]));
        this.allowedFlightProviders = new HashSet<>(((List<String>) args[2]));
        ConversationLog.event(this, "Initialized with service fee " + serviceFeeEur + " EUR");

        DfUtils.registerService(this, "travel-agency", getLocalName() + "-service", null);

        addBehaviour(new CyclicBehaviour() {
            @Override
            public void action() {
                ACLMessage customerMsg = receive(MessageTemplate.MatchPerformative(ACLMessage.CFP));
                if (customerMsg == null) {
                    block();
                    return;
                }
                ConversationLog.received(TravelAgencyAgent.this, customerMsg, "customer CFP received");
                handleCustomerRequest(customerMsg);
            }
        });
    }

    private void handleCustomerRequest(ACLMessage customerCfp) {
        try {
            TripRequest request = (TripRequest) customerCfp.getContentObject();

            HotelProposal hotel = queryBestHotel(request, customerCfp.getConversationId());
            FlightProposal flight = queryBestFlight(request, customerCfp.getConversationId());

            ACLMessage proposal = customerCfp.createReply();
            if (hotel == null || flight == null) {
                proposal.setPerformative(ACLMessage.REFUSE);
                proposal.setContent("Cannot provide full package");
                send(proposal);
                ConversationLog.sent(this, proposal, "cannot build full package");
                return;
            }

            int total = hotel.priceEur() + flight.totalPriceEur() + serviceFeeEur;
            AgencyOffer offer = new AgencyOffer(
                    getLocalName(),
                    hotel.providerName(),
                    hotel.priceEur(),
                    flight.providerName(),
                    flight.totalPriceEur(),
                    serviceFeeEur,
                    total
            );

            proposal.setPerformative(ACLMessage.PROPOSE);
            proposal.setContentObject(offer);
            send(proposal);
            ConversationLog.sent(this, proposal, "offer total=" + total + " EUR");

            waitForDecisionAndPayment(customerCfp.getConversationId(), total, customerCfp.getSender());
        } catch (Exception e) {
            ACLMessage failure = customerCfp.createReply();
            failure.setPerformative(ACLMessage.FAILURE);
            failure.setContent("TravelAgencyAgent error: " + e.getMessage());
            send(failure);
            ConversationLog.sent(this, failure, "exception while handling request");
        }
    }

    private void waitForDecisionAndPayment(String conversationId, int expectedAmount, AID customer) {
        MessageTemplate decisionTemplate = MessageTemplate.and(
                MessageTemplate.MatchConversationId(conversationId),
                MessageTemplate.or(
                        MessageTemplate.MatchPerformative(ACLMessage.ACCEPT_PROPOSAL),
                        MessageTemplate.MatchPerformative(ACLMessage.REJECT_PROPOSAL)
                )
        );
        ACLMessage decision = blockingReceive(decisionTemplate, 15_000);
        if (decision != null) {
            ConversationLog.received(this, decision, "customer decision");
        }
        if (decision == null || decision.getPerformative() == ACLMessage.REJECT_PROPOSAL) {
            return;
        }

        MessageTemplate paymentTemplate = MessageTemplate.and(
                MessageTemplate.MatchConversationId(conversationId + "-payment"),
                MessageTemplate.MatchSender(customer)
        );
        ACLMessage paymentMsg = blockingReceive(paymentTemplate, 10_000);
        if (paymentMsg != null) {
            ConversationLog.received(this, paymentMsg, "payment received");
        }
        if (paymentMsg == null) {
            return;
        }

        ACLMessage confirmation = paymentMsg.createReply();
        try {
            Payment payment = (Payment) paymentMsg.getContentObject();
            if (payment.amountEur() < expectedAmount) {
                confirmation.setPerformative(ACLMessage.FAILURE);
                confirmation.setContent("Payment too low. Expected " + expectedAmount + " EUR");
            } else {
                confirmation.setPerformative(ACLMessage.INFORM);
                confirmation.setContent("Booking completed by " + getLocalName() + " for " + expectedAmount + " EUR");
            }
        } catch (Exception e) {
            confirmation.setPerformative(ACLMessage.FAILURE);
            confirmation.setContent("Payment processing error: " + e.getMessage());
        }
        send(confirmation);
        ConversationLog.sent(this, confirmation, "booking confirmation result");
    }

    private HotelProposal queryBestHotel(TripRequest request, String parentConversationId) {
        List<AID> providers = discoverConnectedProviders("hotel-provider", allowedHotelProviders);
        if (providers.isEmpty()) {
            return null;
        }

        ACLMessage cfp = new ACLMessage(ACLMessage.CFP);
        providers.forEach(cfp::addReceiver);
        cfp.setConversationId(parentConversationId + "-hotel");
        try {
            cfp.setContentObject(request);
        } catch (Exception e) {
            return null;
        }
        send(cfp);
        ConversationLog.sent(this, cfp, "query hotels: " + providers.size() + " providers");

        HotelProposal best = null;
        for (int i = 0; i < providers.size(); i++) {
            ACLMessage reply = blockingReceive(MessageTemplate.MatchConversationId(parentConversationId + "-hotel"), 5_000);
            if (reply != null) {
                ConversationLog.received(this, reply, "hotel provider response");
            }
            if (reply == null || reply.getPerformative() != ACLMessage.PROPOSE) {
                continue;
            }
            try {
                HotelProposal candidate = (HotelProposal) reply.getContentObject();
                if (best == null || candidate.priceEur() < best.priceEur()) {
                    best = candidate;
                }
            } catch (Exception ignored) {
            }
        }
        return best;
    }

    private FlightProposal queryBestFlight(TripRequest request, String parentConversationId) {
        List<AID> providers = discoverConnectedProviders("flight-provider", allowedFlightProviders);
        if (providers.isEmpty()) {
            return null;
        }

        ACLMessage cfp = new ACLMessage(ACLMessage.CFP);
        providers.forEach(cfp::addReceiver);
        cfp.setConversationId(parentConversationId + "-flight");
        try {
            cfp.setContentObject(request);
        } catch (Exception e) {
            return null;
        }
        send(cfp);
        ConversationLog.sent(this, cfp, "query flights: " + providers.size() + " providers");

        FlightProposal best = null;
        for (int i = 0; i < providers.size(); i++) {
            ACLMessage reply = blockingReceive(MessageTemplate.MatchConversationId(parentConversationId + "-flight"), 5_000);
            if (reply != null) {
                ConversationLog.received(this, reply, "flight provider response");
            }
            if (reply == null || reply.getPerformative() != ACLMessage.PROPOSE) {
                continue;
            }
            try {
                FlightProposal candidate = (FlightProposal) reply.getContentObject();
                if (best == null || candidate.totalPriceEur() < best.totalPriceEur()) {
                    best = candidate;
                }
            } catch (Exception ignored) {
            }
        }
        return best;
    }

    private List<AID> discoverConnectedProviders(String serviceType, Set<String> allowedByConfig) {
        List<DFAgentDescription> services = DfUtils.searchByType(this, serviceType);
        List<AID> providerIds = new ArrayList<>();

        for (DFAgentDescription description : services) {
            String providerName = description.getName().getLocalName();
            if (!allowedByConfig.contains(providerName)) {
                continue;
            }

            boolean ownershipMatches = false;
            for (var it = description.getAllServices(); it.hasNext(); ) {
                ServiceDescription sd = (ServiceDescription) it.next();
                if (serviceType.equals(sd.getType()) && getLocalName().equals(sd.getOwnership())) {
                    ownershipMatches = true;
                }
            }
            if (ownershipMatches) {
                providerIds.add(description.getName());
            }
        }
        return providerIds;
    }
}