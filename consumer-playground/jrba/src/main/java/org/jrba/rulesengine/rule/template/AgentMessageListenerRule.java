package org.jrba.rulesengine.rule.template;

import static java.lang.String.format;
import static java.util.Collections.emptyList;
import static java.util.Objects.nonNull;
import static java.util.Optional.ofNullable;
import static org.jrba.rulesengine.constants.FactTypeConstants.MESSAGE;
import static org.jrba.rulesengine.constants.FactTypeConstants.MESSAGES;
import static org.jrba.rulesengine.constants.FactTypeConstants.MESSAGE_CONTENT;
import static org.jrba.rulesengine.constants.FactTypeConstants.MESSAGE_TYPE;
import static org.jrba.rulesengine.constants.FactTypeConstants.RULE_SET_IDX;
import static org.jrba.rulesengine.constants.FactTypeConstants.RULE_STEP;
import static org.jrba.rulesengine.constants.FactTypeConstants.RULE_TYPE;
import static org.jrba.rulesengine.constants.MVELParameterConstants.FACTS;
import static org.jrba.rulesengine.constants.RuleTypeConstants.DEFAULT_MESSAGE_LISTENER_RULE;
import static org.jrba.rulesengine.types.rulesteptype.RuleStepTypeEnum.MESSAGE_READER_PROCESS_CONTENT_STEP;
import static org.jrba.rulesengine.types.rulesteptype.RuleStepTypeEnum.MESSAGE_READER_READ_CONTENT_STEP;
import static org.jrba.rulesengine.types.rulesteptype.RuleStepTypeEnum.MESSAGE_READER_READ_STEP;
import static org.jrba.rulesengine.types.ruletype.AgentRuleTypeEnum.LISTENER;
import static org.jrba.utils.mapper.FactsMapper.mapToRuleSetFacts;
import static org.jrba.utils.messages.MessageReader.readMessageContent;

import java.io.Serializable;
import java.util.ArrayList;
import java.util.List;

import org.jeasy.rules.api.Facts;
import org.jrba.agentmodel.domain.node.AgentNode;
import org.jrba.agentmodel.domain.props.AgentProps;
import org.jrba.rulesengine.RulesController;
import org.jrba.rulesengine.rest.domain.MessageListenerRuleRest;
import org.jrba.rulesengine.rule.AgentBasicRule;
import org.jrba.rulesengine.rule.AgentRule;
import org.jrba.rulesengine.rule.AgentRuleDescription;
import org.jrba.rulesengine.rule.simple.AgentChainRule;
import org.jrba.rulesengine.ruleset.RuleSet;
import org.jrba.rulesengine.ruleset.RuleSetFacts;
import org.mvel2.MVEL;

import jade.lang.acl.ACLMessage;
import jade.lang.acl.MessageTemplate;
import lombok.Getter;

/**
 * Abstract class defining structure of a rule which handles default message retrieval behaviour.
 *
 * @param <E> type of node connected to the Agent
 * @param <T> type of properties of Agent
 */
@Getter
public class AgentMessageListenerRule<T extends AgentProps, E extends AgentNode<T>> extends AgentBasicRule<T, E> {

	protected final RuleSet ruleSet;
	protected Class<?> contentType;
	protected MessageTemplate messageTemplate;
	protected int batchSize;
	protected String handlerRuleType;
	protected Serializable expressionSelectRuleSetIdx;

	/**
	 * Copy constructor.
	 *
	 * @param rule rule that is to be copied
	 */
	public AgentMessageListenerRule(final AgentMessageListenerRule<T, E> rule) {
		super(rule);
		this.ruleSet = rule.getRuleSet();
		this.contentType = rule.getContentType();
		this.messageTemplate = rule.getMessageTemplate();
		this.batchSize = rule.getBatchSize();
		this.handlerRuleType = rule.getHandlerRuleType();
		this.expressionSelectRuleSetIdx = rule.getExpressionSelectRuleSetIdx();
	}

	/**
	 * Constructor
	 *
	 * @param controller      rules controller connected to the agent
	 * @param ruleSet         currently executed rule set
	 * @param contentType     type of content read in the messages
	 * @param template        template used to read messages
	 * @param batchSize       number of messages read at once
	 * @param handlerRuleType rule run when the messages are present
	 */
	protected AgentMessageListenerRule(final RulesController<T, E> controller,
			final RuleSet ruleSet, final Class<?> contentType, final MessageTemplate template, final int batchSize,
			final String handlerRuleType) {
		super(controller);
		this.contentType = contentType;
		this.messageTemplate = template;
		this.ruleSet = ruleSet;
		this.batchSize = batchSize;
		this.handlerRuleType = handlerRuleType;
		initializeSteps();
	}

	/**
	 * Constructor
	 *
	 * @param controller      rules controller connected to the agent
	 * @param ruleSet         currently executed rule set
	 * @param template        template used to read messages
	 * @param batchSize       number of messages read at once
	 * @param handlerRuleType rule run when the messages are present
	 */
	protected AgentMessageListenerRule(final RulesController<T, E> controller, final RuleSet ruleSet,
			final MessageTemplate template, final int batchSize, final String handlerRuleType) {
		super(controller);
		this.contentType = null;
		this.messageTemplate = template;
		this.ruleSet = ruleSet;
		this.batchSize = batchSize;
		this.handlerRuleType = handlerRuleType;
		initializeSteps();
	}

	/**
	 * Constructor
	 *
	 * @param ruleRest rest representation of agent rule
	 * @param ruleSet  currently executed rule set
	 */
	public AgentMessageListenerRule(final MessageListenerRuleRest ruleRest, final RuleSet ruleSet) {
		super(ruleRest);
		try {
			final Serializable msgTemplateExpression = MVEL.compileExpression(
					imports + " " + ruleRest.getMessageTemplate());
			this.messageTemplate = (MessageTemplate) MVEL.executeExpression(msgTemplateExpression);
			this.contentType = Class.forName(ruleRest.getClassName());
			this.ruleSet = ruleSet;
			this.batchSize = ruleRest.getBatchSize();
			this.handlerRuleType = ruleRest.getActionHandler();

			if (nonNull(ruleRest.getSelectRuleSetIdx())) {
				this.expressionSelectRuleSetIdx = MVEL.compileExpression(
						imports + " " + ruleRest.getSelectRuleSetIdx());
			}
			initializeSteps();
		} catch (ClassNotFoundException classNotFoundException) {
			throw new ClassCastException("Content type class was not found!");
		}
		initializeSteps();
	}

	@Override
	public String getAgentRuleType() {
		return LISTENER.getType();
	}

	/**
	 * Method assigns a list of message listener steps.
	 */
	public void initializeSteps() {
		stepRules = new ArrayList<>(
				List.of(new ReadMessagesRule(), new ReadMessagesContentRule(), new HandleMessageRule()));
	}

	@Override
	public List<AgentRule> getRules() {
		return stepRules;
	}

	@Override
	public void connectToController(final RulesController<?, ?> rulesController) {
		super.connectToController(rulesController);
		stepRules.forEach(rule -> rule.connectToController(rulesController));
	}

	/**
	 * Method can be optionally overwritten in order to change rule set based on facts after reading message content.
	 *
	 * @param facts facts from which the rule set index is to be selected
	 * @return number indicating rule set index
	 */
	protected int selectRuleSetIdx(final RuleSetFacts facts) {
		return facts.get(RULE_SET_IDX);
	}

	@Override
	public AgentRuleDescription initializeRuleDescription() {
		return new AgentRuleDescription(DEFAULT_MESSAGE_LISTENER_RULE,
				"default message listener rule",
				"default implementation of a rule that listens and processes new messages received by an agent");
	}

	@Override
	public AgentRule copy() {
		return new AgentMessageListenerRule<>(this);
	}

	// RULE EXECUTED WHEN AGENT RECEIVES TRIGGER ABOUT NEW MESSAGES RECEIVED
	class ReadMessagesRule extends AgentBasicRule<T, E> {

		public ReadMessagesRule() {
			super(AgentMessageListenerRule.this.controller);
			this.isRuleStep = true;
		}

		@Override
		public void executeRule(final RuleSetFacts facts) {
			final List<ACLMessage> messages = agent.receive(messageTemplate, batchSize);
			facts.put(MESSAGES, ofNullable(messages).orElse(emptyList()));
		}

		@Override
		public AgentRuleDescription initializeRuleDescription() {
			return new AgentRuleDescription(AgentMessageListenerRule.this.ruleType, MESSAGE_READER_READ_STEP,
					format("%s - read messages", AgentMessageListenerRule.this.name),
					"when new message event is triggerred, agent attempts to read messages corresponding to "
							+ "selected template");
		}

		@Override
		public AgentRule copy() {
			return new ReadMessagesRule();
		}
	}

	// RULE EXECUTED WHEN AGENT READS THE CONTENT OF RECEIVED MESSAGES
	class ReadMessagesContentRule extends AgentChainRule<T, E> {

		public ReadMessagesContentRule() {
			super(AgentMessageListenerRule.this.controller, AgentMessageListenerRule.this.ruleSet);
			this.isRuleStep = true;
		}

		@Override
		public void executeRule(final RuleSetFacts facts) {
			final ACLMessage message = facts.get(MESSAGE);

			if (nonNull(contentType)) {
				final Object content = readMessageContent(message, contentType);
				facts.put(MESSAGE_CONTENT, content);
			}
			if (nonNull(AgentMessageListenerRule.this.initialParameters)) {
				AgentMessageListenerRule.this.initialParameters.replace(FACTS, facts);
			}

			int ruleSetIdx = selectRuleSetIdx(facts);

			if (nonNull(expressionSelectRuleSetIdx)) {
				ruleSetIdx = (int) MVEL.executeExpression(expressionSelectRuleSetIdx,
						AgentMessageListenerRule.this.initialParameters);
			}

			facts.put(RULE_SET_IDX, ruleSetIdx);
			facts.put(MESSAGE_TYPE, ofNullable(message.getConversationId()).orElse(""));
			facts.put(RULE_STEP, MESSAGE_READER_PROCESS_CONTENT_STEP.getType());
		}

		@Override
		public AgentRuleDescription initializeRuleDescription() {
			return new AgentRuleDescription(AgentMessageListenerRule.this.ruleType,
					MESSAGE_READER_READ_CONTENT_STEP,
					format("%s - read message content", AgentMessageListenerRule.this.name),
					"when new message matching given template is present, then agent reads its content");
		}

		@Override
		public AgentRule copy() {
			return new ReadMessagesContentRule();
		}
	}

	// RULE EXECUTED WHEN AFTER AGENT READS A MESSAGE AND PROCEEDS TO ITS HANDLING
	class HandleMessageRule extends AgentBasicRule<T, E> {

		public HandleMessageRule() {
			super(AgentMessageListenerRule.this.controller);
			this.isRuleStep = true;
		}

		@Override
		public boolean evaluateRule(final RuleSetFacts facts) {
			return true;
		}

		@Override
		public void execute(final Facts facts) {
			final RuleSetFacts triggerFacts = mapToRuleSetFacts(facts);
			triggerFacts.put(RULE_TYPE, handlerRuleType);
			controller.fire(triggerFacts);
		}

		@Override
		public AgentRuleDescription initializeRuleDescription() {
			return new AgentRuleDescription(AgentMessageListenerRule.this.ruleType,
					MESSAGE_READER_PROCESS_CONTENT_STEP,
					format("%s - handle message", AgentMessageListenerRule.this.name),
					"when agent reads message of given type, its handler is run");
		}

		@Override
		public AgentRule copy() {
			return new HandleMessageRule();
		}
	}

}
