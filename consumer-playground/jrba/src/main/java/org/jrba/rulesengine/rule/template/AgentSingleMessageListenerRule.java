package org.jrba.rulesengine.rule.template;

import static java.lang.Long.parseLong;
import static java.lang.String.format;
import static java.util.Objects.isNull;
import static java.util.Objects.nonNull;
import static org.jrba.rulesengine.constants.FactTypeConstants.MESSAGE_EXPIRATION;
import static org.jrba.rulesengine.constants.FactTypeConstants.MESSAGE_TEMPLATE;
import static org.jrba.rulesengine.constants.FactTypeConstants.RECEIVED_MESSAGE;
import static org.jrba.rulesengine.constants.MVELParameterConstants.FACTS;
import static org.jrba.rulesengine.constants.MVELParameterConstants.MESSAGE;
import static org.jrba.rulesengine.constants.RuleTypeConstants.DEFAULT_SINGLE_MESSAGE_LISTENER_RULE;
import static org.jrba.rulesengine.types.rulesteptype.RuleStepTypeEnum.SINGLE_MESSAGE_READER_CREATE_STEP;
import static org.jrba.rulesengine.types.rulesteptype.RuleStepTypeEnum.SINGLE_MESSAGE_READER_HANDLE_MESSAGE_STEP;
import static org.jrba.rulesengine.types.ruletype.AgentRuleTypeEnum.LISTENER_SINGLE;

import java.io.Serializable;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

import org.jrba.agentmodel.domain.node.AgentNode;
import org.jrba.agentmodel.domain.props.AgentProps;
import org.jrba.rulesengine.RulesController;
import org.jrba.rulesengine.rest.domain.SingleMessageListenerRuleRest;
import org.jrba.rulesengine.rule.AgentBasicRule;
import org.jrba.rulesengine.rule.AgentRule;
import org.jrba.rulesengine.rule.AgentRuleDescription;
import org.jrba.rulesengine.ruleset.RuleSetFacts;
import org.mvel2.MVEL;

import jade.lang.acl.ACLMessage;
import jade.lang.acl.MessageTemplate;
import lombok.Getter;

/**
 * Abstract class defining structure of a rule which handles default single message retrieval behaviour.
 *
 * @param <E> type of node connected to the Agent
 * @param <T> type of properties of Agent
 */
@Getter
public class AgentSingleMessageListenerRule<T extends AgentProps, E extends AgentNode<T>> extends AgentBasicRule<T, E> {

	protected Serializable expressionConstructMessageTemplate;
	protected Serializable expressionSpecifyExpirationTime;
	protected Serializable expressionHandleMessageProcessing;

	/**
	 * Compiled MVEL expression called when the timout is triggered and no message was received.
	 */
	protected Serializable expressionHandleMessageNotReceived;

	/**
	 * Copy constructor.
	 *
	 * @param rule rule that is to be copied
	 */
	public AgentSingleMessageListenerRule(final AgentSingleMessageListenerRule<T, E> rule) {
		super(rule);
		this.expressionConstructMessageTemplate = rule.getExpressionConstructMessageTemplate();
		this.expressionSpecifyExpirationTime = rule.getExpressionSpecifyExpirationTime();
		this.expressionHandleMessageProcessing = rule.getExpressionHandleMessageProcessing();
		this.expressionHandleMessageNotReceived = rule.getExpressionHandleMessageNotReceived();
	}

	/**
	 * Constructor
	 *
	 * @param controller rules controller connected to the agent
	 */
	protected AgentSingleMessageListenerRule(final RulesController<T, E> controller) {
		super(controller);
		initializeSteps();
	}

	/**
	 * Constructor
	 *
	 * @param ruleRest rest representation of agent rule
	 */
	public AgentSingleMessageListenerRule(final SingleMessageListenerRuleRest ruleRest) {
		super(ruleRest);
		if (nonNull(ruleRest.getConstructMessageTemplate())) {
			this.expressionConstructMessageTemplate = MVEL.compileExpression(
					imports + " " + ruleRest.getConstructMessageTemplate());
		}
		if (nonNull(ruleRest.getSpecifyExpirationTime())) {
			this.expressionSpecifyExpirationTime = MVEL.compileExpression(
					imports + " " + ruleRest.getSpecifyExpirationTime());
		}
		if (nonNull(ruleRest.getHandleMessageProcessing())) {
			this.expressionHandleMessageProcessing = MVEL.compileExpression(
					imports + " " + ruleRest.getHandleMessageProcessing());
		}
		if (nonNull(ruleRest.getHandleMessageNotReceived())) {
			this.expressionHandleMessageNotReceived = MVEL.compileExpression(
					imports + " " + ruleRest.getHandleMessageNotReceived());
		}
		initializeSteps();
	}

	/**
	 * Method assigns a list of single message listener rule steps.
	 */
	public void initializeSteps() {
		stepRules = new ArrayList<>(List.of(
				new CreateSingleMessageListenerRule(),
				new HandleReceivedMessageRule()
		));
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

	@Override
	public String getAgentRuleType() {
		return LISTENER_SINGLE.getType();
	}

	/**
	 * Method construct template used to retrieve the message.
	 *
	 * @param facts facts with additional parameters
	 * @return template that the retrieved message should match
	 */
	protected MessageTemplate constructMessageTemplate(final RuleSetFacts facts) {
		return MessageTemplate.MatchAll();
	}

	/**
	 * Method specifies the time after which the message will not be processed.
	 *
	 * @param facts facts with additional parameters
	 * @return number of milliseconds specifying the waiting limit for the message retrieval
	 */
	protected long specifyExpirationTime(final RuleSetFacts facts) {
		return 0;
	}

	/**
	 * Method defines handler used to process received message.
	 *
	 * @param facts   facts with additional parameters
	 * @param message retrieved message
	 */
	protected void handleMessageProcessing(final ACLMessage message, final RuleSetFacts facts) {
		// TO BE OVERRIDDEN BY USER
	}

	/**
	 * Method handles case when message was not received on time.
	 *
	 * @param facts facts with additional parameters
	 */
	protected void handleMessageNotReceived(final RuleSetFacts facts) {
		// TO BE OVERRIDDEN BY USER
	}

	@Override
	public AgentRuleDescription initializeRuleDescription() {
		return new AgentRuleDescription(DEFAULT_SINGLE_MESSAGE_LISTENER_RULE,
				"default single-time message listener rule",
				"default implementation of a rule that listens for a single message matching a given template");
	}

	@Override
	public AgentRule copy() {
		return new AgentSingleMessageListenerRule<>(this);
	}

	// RULE EXECUTED WHEN SINGLE MESSAGE LISTENER IS BEING INITIATED
	class CreateSingleMessageListenerRule extends AgentBasicRule<T, E> {

		public CreateSingleMessageListenerRule() {
			super(AgentSingleMessageListenerRule.this.controller);
			this.isRuleStep = true;
		}

		@Override
		public void executeRule(final RuleSetFacts facts) {
			if (nonNull(AgentSingleMessageListenerRule.this.initialParameters)) {
				AgentSingleMessageListenerRule.this.initialParameters.replace(FACTS, facts);
			}

			final MessageTemplate messageTemplate = isNull(expressionConstructMessageTemplate) ?
					constructMessageTemplate(facts) :
					(MessageTemplate) MVEL.executeExpression(expressionConstructMessageTemplate,
							AgentSingleMessageListenerRule.this.initialParameters);
			final long expirationDuration = isNull(expressionSpecifyExpirationTime) ?
					specifyExpirationTime(facts) :
					parseLong(MVEL.executeExpression(expressionSpecifyExpirationTime,
							AgentSingleMessageListenerRule.this.initialParameters).toString());

			facts.put(MESSAGE_TEMPLATE, messageTemplate);
			facts.put(MESSAGE_EXPIRATION, expirationDuration);
		}

		@Override
		public AgentRuleDescription initializeRuleDescription() {
			return new AgentRuleDescription(AgentSingleMessageListenerRule.this.ruleType,
					SINGLE_MESSAGE_READER_CREATE_STEP,
					format("%s - initialization of behaviour", AgentSingleMessageListenerRule.this.name),
					"rule constructs message template and specifies expiration duration");
		}

		@Override
		public AgentRule copy() {
			return new CreateSingleMessageListenerRule();
		}
	}

	// RULE EXECUTED WHEN MESSAGE IS RECEIVED
	class HandleReceivedMessageRule extends AgentBasicRule<T, E> {

		public HandleReceivedMessageRule() {
			super(AgentSingleMessageListenerRule.this.controller);
			this.isRuleStep = true;
		}

		@Override
		public void executeRule(final RuleSetFacts facts) {
			final Optional<ACLMessage> receivedMessage = facts.get(RECEIVED_MESSAGE);
			if (nonNull(AgentSingleMessageListenerRule.this.initialParameters)) {
				AgentSingleMessageListenerRule.this.initialParameters.replace(FACTS, facts);
			}

			if (receivedMessage.isEmpty()) {
				if (isNull(expressionHandleMessageNotReceived)) {
					handleMessageNotReceived(facts);
				} else {
					MVEL.executeExpression(expressionHandleMessageNotReceived,
							AgentSingleMessageListenerRule.this.initialParameters);
				}
				return;
			}

			receivedMessage.ifPresent(message -> {
				if (isNull(expressionHandleMessageProcessing)) {
					handleMessageProcessing(message, facts);
				} else {
					AgentSingleMessageListenerRule.this.initialParameters.put(MESSAGE, message);
					MVEL.executeExpression(expressionHandleMessageProcessing,
							AgentSingleMessageListenerRule.this.initialParameters);
					AgentSingleMessageListenerRule.this.initialParameters.remove(MESSAGE);
				}
			});
		}

		@Override
		public AgentRuleDescription initializeRuleDescription() {
			return new AgentRuleDescription(AgentSingleMessageListenerRule.this.ruleType,
					SINGLE_MESSAGE_READER_HANDLE_MESSAGE_STEP,
					format("%s - handling received message", AgentSingleMessageListenerRule.this.name),
					"rule triggers method which handles received message");
		}

		@Override
		public AgentRule copy() {
			return new HandleReceivedMessageRule();
		}
	}
}
