package org.jrba.utils.messages;

import static jade.lang.acl.ACLMessage.UNKNOWN;
import static java.lang.Integer.parseInt;
import static java.util.Arrays.stream;
import static org.jrba.utils.mapper.JsonMapper.getMapper;

import java.util.Collection;
import java.util.UUID;
import java.util.function.Consumer;

import org.jrba.exception.IncorrectMessageContentException;

import com.fasterxml.jackson.core.JsonProcessingException;

import jade.core.AID;
import jade.lang.acl.ACLMessage;

/**
 * Class used to build ACL messages.
 */
public class MessageBuilder {

	private ACLMessage aclMessage;

	private MessageBuilder(final Integer ruleIdx, final Integer performative) {
		aclMessage = new ACLMessage(performative);
		aclMessage.setOntology(ruleIdx.toString());
	}

	/**
	 * Builder creator.
	 *
	 * @param ruleIdx      index of the rule set
	 * @return MessageBuilder
	 */
	public static MessageBuilder builder(final Integer ruleIdx) {
		return new MessageBuilder(ruleIdx, UNKNOWN);
	}

	/**
	 * Builder creator.
	 *
	 * @param ruleIdx      index of the rule set
	 * @param performative performative of the message
	 * @return MessageBuilder
	 */
	public static MessageBuilder builder(final Integer ruleIdx, final Integer performative) {
		return new MessageBuilder(ruleIdx, performative);
	}

	/**
	 * Builder creator.
	 *
	 * @param ruleIdx      index of the rule set
	 * @param performative performative of the message
	 * @return MessageBuilder
	 */
	public static MessageBuilder builder(final String ruleIdx, final Integer performative) {
		return new MessageBuilder(parseInt(ruleIdx), performative);
	}

	/**
	 * Method assigns protocol of the message.
	 *
	 * @param messageProtocol protocol to be assigned
	 * @return MessageBuilder
	 */
	public MessageBuilder withMessageProtocol(final String messageProtocol) {
		this.aclMessage.setProtocol(messageProtocol);
		return this;
	}

	/**
	 * Method assigns ontology of the message.
	 *
	 * @param messageOntology ontology to be assigned
	 * @return MessageBuilder
	 */
	public MessageBuilder withOntology(final String messageOntology) {
		this.aclMessage.setOntology(messageOntology);
		return this;
	}

	/**
	 * Method assigns conversationId of the message.
	 *
	 * @param conversationId conversationId to be assigned
	 * @return MessageBuilder
	 */
	public MessageBuilder withConversationId(final String conversationId) {
		this.aclMessage.setConversationId(conversationId);
		return this;
	}

	/**
	 * Method generates replyWith of the message.
	 *
	 * @return MessageBuilder
	 */
	public MessageBuilder withGeneratedReplyWith() {
		final String replyWith = UUID.randomUUID().toString();
		this.aclMessage.setReplyWith(replyWith);
		return this;
	}

	/**
	 * Method assigns content (String) of the message.
	 *
	 * @param content content to be assigned
	 * @return MessageBuilder
	 */
	public MessageBuilder withStringContent(final String content) {
		this.aclMessage.setContent(content);
		return this;
	}

	/**
	 * Method assigns content (Object) of the message.
	 *
	 * @param content content to be assigned
	 * @return MessageBuilder
	 */
	public MessageBuilder withObjectContent(final Object content) {
		try {
			this.aclMessage.setContent(getMapper().writeValueAsString(content));
		} catch (JsonProcessingException e) {
			throw new IncorrectMessageContentException();
		}
		return this;
	}

	/**
	 * Method assigns content (Object) of the message.
	 *
	 * @param content      content to be assigned
	 * @param errorHandler handler executed when the incorrect message content was passed
	 * @return MessageBuilder
	 */
	public MessageBuilder withObjectContent(final Object content, final Consumer<Exception> errorHandler) {
		try {
			this.aclMessage.setContent(getMapper().writeValueAsString(content));
		} catch (JsonProcessingException e) {
			errorHandler.accept(e);
		}
		return this;
	}

	/**
	 * Method assigns performative of the message.
	 *
	 * @param performative performative to be assigned
	 * @return MessageBuilder
	 */
	public MessageBuilder withPerformative(final Integer performative) {
		this.aclMessage.setPerformative(performative);
		return this;
	}

	/**
	 * Method assigns replyWith of the message.
	 *
	 * @param replyWith replyWith to be assigned
	 * @return MessageBuilder
	 */
	public MessageBuilder withReplyWith(final String replyWith) {
		this.aclMessage.setReplyWith(replyWith);
		return this;
	}

	/**
	 * Method assigns sender of the message.
	 *
	 * @param sender sender to be assigned
	 * @return MessageBuilder
	 */
	public MessageBuilder withSender(final AID sender) {
		this.aclMessage.setSender(sender);
		return this;
	}

	/**
	 * Method adds receivers of the message.
	 *
	 * @param aids aids of the receivers to be assigned
	 * @return MessageBuilder
	 */
	public MessageBuilder withReceivers(final AID... aids) {
		stream(aids).forEach(aclMessage::addReceiver);
		return this;
	}

	/**
	 * Method assigns new receivers of the message.
	 *
	 * @param aids aids of the receivers to be assigned
	 * @return MessageBuilder
	 */
	public MessageBuilder withNewReceivers(final AID... aids) {
		aclMessage.clearAllReceiver();
		stream(aids).forEach(aclMessage::addReceiver);
		return this;
	}

	/**
	 * Method adds receivers of the message.
	 *
	 * @param aids aids of the receivers to be assigned
	 * @return MessageBuilder
	 */
	public MessageBuilder withReceivers(final Collection<AID> aids) {
		aids.forEach(aclMessage::addReceiver);
		return this;
	}

	/**
	 * Method creates a copy of the message
	 *
	 * @param message message to be copied
	 * @return MessageBuilder
	 */
	public MessageBuilder copy(final ACLMessage message) {
		this.aclMessage = (ACLMessage) message.clone();
		return this;
	}

	/**
	 * Builds the ACLMessage.
	 *
	 * @return built message
	 */
	public ACLMessage build() {
		return aclMessage;
	}
}
