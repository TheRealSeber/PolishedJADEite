// START GENAI
package pw.agents;

import jade.core.Agent;
import jade.lang.acl.ACLMessage;

final class ConversationLog {
    private ConversationLog() {
    }

    static void event(Agent agent, String text) {
        System.out.printf("[%-14s] %s%n", agent.getLocalName(), text);
    }

    static void sent(Agent agent, ACLMessage msg, String details) {
        String receiver = msg.getAllReceiver().hasNext() ? "multiple" : "none";
        System.out.printf(
                "[%-14s] SENT %-16s conv=%s to=%s %s%n",
                agent.getLocalName(),
                ACLMessage.getPerformative(msg.getPerformative()),
                msg.getConversationId(),
                receiver,
                details == null ? "" : details
        );
    }

    static void received(Agent agent, ACLMessage msg, String details) {
        String sender = msg.getSender() == null ? "unknown" : msg.getSender().getLocalName();
        System.out.printf(
                "[%-14s] RECV %-16s conv=%s from=%s %s%n",
                agent.getLocalName(),
                ACLMessage.getPerformative(msg.getPerformative()),
                msg.getConversationId(),
                sender,
                details == null ? "" : details
        );
    }
}
// END GENAI