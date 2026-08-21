package org.jrba.rulesengine.rule.template;

import static java.lang.String.format;
import static java.util.Objects.isNull;
import static java.util.Objects.nonNull;
import static org.jrba.rulesengine.constants.FactTypeConstants.REQUEST_CREATE_MESSAGE;
import static org.jrba.rulesengine.constants.FactTypeConstants.REQUEST_FAILURE_MESSAGE;
import static org.jrba.rulesengine.constants.FactTypeConstants.REQUEST_FAILURE_RESULTS_MESSAGES;
import static org.jrba.rulesengine.constants.FactTypeConstants.REQUEST_INFORM_MESSAGE;
import static org.jrba.rulesengine.constants.FactTypeConstants.REQUEST_INFORM_RESULTS_MESSAGES;
import static org.jrba.rulesengine.constants.FactTypeConstants.REQUEST_REFUSE_MESSAGE;
import static org.jrba.rulesengine.constants.FactTypeConstants.RULE_SET_IDX;
import static org.jrba.rulesengine.constants.MVELParameterConstants.FACTS;
import static org.jrba.rulesengine.constants.MVELParameterConstants.FAILURE;
import static org.jrba.rulesengine.constants.MVELParameterConstants.FAILURE_RESULTS;
import static org.jrba.rulesengine.constants.MVELParameterConstants.INFORM;
import static org.jrba.rulesengine.constants.MVELParameterConstants.INFORM_RESULTS;
import static org.jrba.rulesengine.constants.MVELParameterConstants.REFUSE;
import static org.jrba.rulesengine.constants.RuleTypeConstants.DEFAULT_REQUEST_RULE;
import static org.jrba.rulesengine.types.rulesteptype.RuleStepTypeEnum.REQUEST_CREATE_STEP;
import static org.jrba.rulesengine.types.rulesteptype.RuleStepTypeEnum.REQUEST_HANDLE_ALL_RESULTS_STEP;
import static org.jrba.rulesengine.types.rulesteptype.RuleStepTypeEnum.REQUEST_HANDLE_FAILURE_STEP;
import static org.jrba.rulesengine.types.rulesteptype.RuleStepTypeEnum.REQUEST_HANDLE_INFORM_STEP;
import static org.jrba.rulesengine.types.rulesteptype.RuleStepTypeEnum.REQUEST_HANDLE_REFUSE_STEP;
import static org.jrba.rulesengine.types.ruletype.AgentRuleTypeEnum.REQUEST;

import java.io.Serializable;
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;

import org.jrba.agentmodel.domain.node.AgentNode;
import org.jrba.agentmodel.domain.props.AgentProps;
import org.jrba.rulesengine.RulesController;
import org.jrba.rulesengine.rest.domain.RequestRuleRest;
import org.jrba.rulesengine.rule.AgentBasicRule;
import org.jrba.rulesengine.rule.AgentRule;
import org.jrba.rulesengine.rule.AgentRuleDescription;
import org.jrba.rulesengine.ruleset.RuleSetFacts;
import org.jrba.utils.messages.MessageBuilder;
import org.mvel2.MVEL;

import jade.lang.acl.ACLMessage;
import lombok.Getter;

/**
 * Abstract class defining structure of a rule which handles default Request initiator behaviour.
 *
 * @param <E> type of node connected to the Agent
 * @param <T> type of properties of Agent
 */
@Getter
public class AgentRequestRule<T extends AgentProps, E extends AgentNode<T>> extends AgentBasicRule<T, E> {

	protected Serializable expressionCreateRequestMessage;
	protected Serializable expressionEvaluateBeforeForAll;
	protected Serializable expressionHandleInform;
	protected Serializable expressionHandleRefuse;
	protected Serializable expressionHandleFailure;
	protected Serializable expressionHandleAllResults;

	/**
	 * Copy constructor.
	 *
	 * @param rule rule that is to be copied
	 */
	public AgentRequestRule(final AgentRequestRule<T, E> rule) {
		super(rule);
		this.expressionCreateRequestMessage = rule.getExpressionCreateRequestMessage();
		this.expressionEvaluateBeforeForAll = rule.getExpressionEvaluateBeforeForAll();
		this.expressionHandleInform = rule.getExpressionHandleInform();
		this.expressionHandleRefuse = rule.getExpressionHandleRefuse();
		this.expressionHandleFailure = rule.getExpressionHandleFailure();
		this.expressionHandleAllResults = rule.getExpressionHandleAllResults();
	}

	/**
	 * Constructor
	 *
	 * @param controller rules controller connected to the agent
	 */
	protected AgentRequestRule(final RulesController<T, E> controller) {
		super(controller);
		initializeSteps();
	}

	/**
	 * Constructor
	 *
	 * @param ruleRest rest representation of agent rule
	 */
	public AgentRequestRule(final RequestRuleRest ruleRest) {
		super(ruleRest);
		if (nonNull(ruleRest.getCreateRequestMessage())) {
			this.expressionCreateRequestMessage = MVEL.compileExpression(
					imports + " " + ruleRest.getCreateRequestMessage());
		}
		if (nonNull(ruleRest.getEvaluateBeforeForAll())) {
			this.expressionEvaluateBeforeForAll = MVEL.compileExpression(
					imports + " " + ruleRest.getEvaluateBeforeForAll());
		}
		if (nonNull(ruleRest.getHandleInform())) {
			this.expressionHandleInform = MVEL.compileExpression(imports + " " + ruleRest.getHandleInform());
		}
		if (nonNull(ruleRest.getHandleFailure())) {
			this.expressionHandleFailure = MVEL.compileExpression(imports + " " + ruleRest.getHandleFailure());
		}
		if (nonNull(ruleRest.getHandleAllResults())) {
			this.expressionHandleAllResults = MVEL.compileExpression(imports + " " + ruleRest.getHandleAllResults());
		}
		if (nonNull(ruleRest.getHandleRefuse())) {
			this.expressionHandleRefuse = MVEL.compileExpression(imports + " " + ruleRest.getHandleRefuse());
		}
		initializeSteps();
	}

	/**
	 * Method assigns a list of REQUEST protocol steps.
	 */
	public void initializeSteps() {
		stepRules = new ArrayList<>(List.of(
				new CreateRequestMessageRule(),
				new HandleInformRule(),
				new HandleRefuseRule(),
				new HandleFailureRule(),
				new HandleAllResponsesRule()));
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
		return REQUEST.getType();
	}

	/**
	 * Method executed when request message is to be created.
	 *
	 * @param facts facts with additional parameters
	 * @return initialized request message
	 */
	protected ACLMessage createRequestMessage(final RuleSetFacts facts) {
		return MessageBuilder.builder(facts.get(RULE_SET_IDX).toString(), ACLMessage.REQUEST).build();
	}

	/**
	 * Method evaluates if the action should be executed upon any message received.
	 *
	 * @param facts facts with additional parameters
	 * @return boolean indicating if the rule is to be triggered
	 */
	protected boolean evaluateBeforeForAll(final RuleSetFacts facts) {
		return true;
	}

	/**
	 * Method executed when INFORM message is to be handled.
	 *
	 * @param facts  facts with additional parameters
	 * @param inform received INFORM message
	 */
	protected void handleInform(final ACLMessage inform, final RuleSetFacts facts) {
		// TO BE OVERRIDDEN BY USER
	}

	/**
	 * Method executed when REFUSE message is to be handled.
	 *
	 * @param facts  facts with additional parameters
	 * @param refuse received REFUSE message
	 */
	protected void handleRefuse(final ACLMessage refuse, final RuleSetFacts facts) {
		// TO BE OVERRIDDEN BY USER
	}

	/**
	 * Method executed when FAILURE message is to be handled.
	 *
	 * @param facts   facts with additional parameters
	 * @param failure received FAILURE message
	 */
	protected void handleFailure(final ACLMessage failure, final RuleSetFacts facts) {
		// TO BE OVERRIDDEN BY USER
	}

	/**
	 * Optional method executed when ALL RESULT messages are to be handled.
	 *
	 * @param facts    facts with additional parameters
	 * @param failures list of FAILURE messages
	 * @param informs  list of INFORM messages
	 */
	protected void handleAllResults(final Collection<ACLMessage> informs, final Collection<ACLMessage> failures,
			final RuleSetFacts facts) {
		// TO BE OVERRIDDEN BY USER
	}

	@Override
	public AgentRuleDescription initializeRuleDescription() {
		return new AgentRuleDescription(DEFAULT_REQUEST_RULE,
				"default request rule",
				"default implementation of a rule that handles each step of FIPA REQUEST protocol");
	}

	@Override
	public AgentRule copy() {
		return new AgentRequestRule<>(this);
	}

	// RULE EXECUTED WHEN REQUEST MESSAGE IS TO BE CREATED
	class CreateRequestMessageRule extends AgentBasicRule<T, E> {

		public CreateRequestMessageRule() {
			super(AgentRequestRule.this.controller);
			this.isRuleStep = true;
		}

		@Override
		public void executeRule(final RuleSetFacts facts) {
			if (nonNull(AgentRequestRule.this.initialParameters)) {
				AgentRequestRule.this.initialParameters.replace(FACTS, facts);
			}

			final ACLMessage request = isNull(expressionCreateRequestMessage) ?
					createRequestMessage(facts) :
					(ACLMessage) MVEL.executeExpression(expressionCreateRequestMessage,
							AgentRequestRule.this.initialParameters);
			facts.put(REQUEST_CREATE_MESSAGE, request);
		}

		@Override
		public AgentRuleDescription initializeRuleDescription() {
			return new AgentRuleDescription(AgentRequestRule.this.ruleType, REQUEST_CREATE_STEP,
					format("%s - create request message", AgentRequestRule.this.name),
					"rule performed a when request message sent to other agents is to be created");
		}

		@Override
		public AgentRule copy() {
			return new CreateRequestMessageRule();
		}
	}

	// RULE EXECUTED WHEN INFORM MESSAGE IS RECEIVED
	class HandleInformRule extends AgentBasicRule<T, E> {

		public HandleInformRule() {
			super(AgentRequestRule.this.controller);
			this.isRuleStep = true;
		}

		@Override
		public boolean evaluateRule(final RuleSetFacts facts) {
			if (nonNull(AgentRequestRule.this.initialParameters)) {
				AgentRequestRule.this.initialParameters.replace(FACTS, facts);
			}

			return isNull(expressionEvaluateBeforeForAll) ?
					evaluateBeforeForAll(facts) :
					(boolean) MVEL.executeExpression(expressionEvaluateBeforeForAll,
							AgentRequestRule.this.initialParameters);
		}

		@Override
		public void executeRule(final RuleSetFacts facts) {
			final ACLMessage inform = facts.get(REQUEST_INFORM_MESSAGE);
			if (nonNull(AgentRequestRule.this.initialParameters)) {
				AgentRequestRule.this.initialParameters.replace(FACTS, facts);
			}

			if (isNull(expressionHandleInform)) {
				handleInform(inform, facts);
			} else {
				AgentRequestRule.this.initialParameters.put(INFORM, inform);
				MVEL.executeExpression(expressionHandleInform, AgentRequestRule.this.initialParameters);
				AgentRequestRule.this.initialParameters.remove(INFORM);
			}
		}

		@Override
		public AgentRuleDescription initializeRuleDescription() {
			return new AgentRuleDescription(AgentRequestRule.this.ruleType, REQUEST_HANDLE_INFORM_STEP,
					format("%s - handle inform message", AgentRequestRule.this.name),
					"rule that handles case when INFORM message is received");
		}

		@Override
		public AgentRule copy() {
			return new HandleInformRule();
		}
	}

	// RULE EXECUTED WHEN REFUSE MESSAGE IS RECEIVED
	class HandleRefuseRule extends AgentBasicRule<T, E> {

		public HandleRefuseRule() {
			super(AgentRequestRule.this.controller);
			this.isRuleStep = true;
		}

		@Override
		public boolean evaluateRule(final RuleSetFacts facts) {
			if (nonNull(AgentRequestRule.this.initialParameters)) {
				AgentRequestRule.this.initialParameters.replace(FACTS, facts);
			}

			return isNull(expressionEvaluateBeforeForAll) ?
					evaluateBeforeForAll(facts) :
					(boolean) MVEL.executeExpression(expressionEvaluateBeforeForAll,
							AgentRequestRule.this.initialParameters);
		}

		@Override
		public void executeRule(final RuleSetFacts facts) {
			final ACLMessage refuse = facts.get(REQUEST_REFUSE_MESSAGE);
			if (nonNull(AgentRequestRule.this.initialParameters)) {
				AgentRequestRule.this.initialParameters.replace(FACTS, facts);
			}

			if (isNull(expressionHandleRefuse)) {
				handleRefuse(refuse, facts);
			} else {
				AgentRequestRule.this.initialParameters.put(REFUSE, refuse);
				MVEL.executeExpression(expressionHandleRefuse, AgentRequestRule.this.initialParameters);
				AgentRequestRule.this.initialParameters.remove(REFUSE);
			}
		}

		@Override
		public AgentRuleDescription initializeRuleDescription() {
			return new AgentRuleDescription(AgentRequestRule.this.ruleType, REQUEST_HANDLE_REFUSE_STEP,
					format("%s - handle refuse message", AgentRequestRule.this.name),
					"rule that handles case when REFUSE message is received");
		}

		@Override
		public AgentRule copy() {
			return new HandleRefuseRule();
		}
	}

	// RULE EXECUTED WHEN FAILURE MESSAGE IS RECEIVED
	class HandleFailureRule extends AgentBasicRule<T, E> {

		public HandleFailureRule() {
			super(AgentRequestRule.this.controller);
			this.isRuleStep = true;
		}

		@Override
		public boolean evaluateRule(final RuleSetFacts facts) {
			if (nonNull(AgentRequestRule.this.initialParameters)) {
				AgentRequestRule.this.initialParameters.replace(FACTS, facts);
			}

			return isNull(expressionEvaluateBeforeForAll) ?
					evaluateBeforeForAll(facts) :
					(boolean) MVEL.executeExpression(expressionEvaluateBeforeForAll,
							AgentRequestRule.this.initialParameters);
		}

		@Override
		public void executeRule(final RuleSetFacts facts) {
			final ACLMessage failure = facts.get(REQUEST_FAILURE_MESSAGE);
			if (nonNull(AgentRequestRule.this.initialParameters)) {
				AgentRequestRule.this.initialParameters.replace(FACTS, facts);
			}

			if (isNull(expressionHandleFailure)) {
				handleFailure(failure, facts);
			} else {
				AgentRequestRule.this.initialParameters.put(FAILURE, failure);
				MVEL.executeExpression(expressionHandleFailure, AgentRequestRule.this.initialParameters);
				AgentRequestRule.this.initialParameters.remove(FAILURE);
			}
		}

		@Override
		public AgentRuleDescription initializeRuleDescription() {
			return new AgentRuleDescription(AgentRequestRule.this.ruleType, REQUEST_HANDLE_FAILURE_STEP,
					format("%s - handle failure message", AgentRequestRule.this.name),
					"rule that handles case when FAILURE message is received");
		}

		@Override
		public AgentRule copy() {
			return new HandleFailureRule();
		}
	}

	// RULE EXECUTED WHEN ALL FAILURE AND INFORM MESSAGES ARE RECEIVED
	class HandleAllResponsesRule extends AgentBasicRule<T, E> {

		public HandleAllResponsesRule() {
			super(AgentRequestRule.this.controller);
			this.isRuleStep = true;
		}

		@Override
		public boolean evaluateRule(final RuleSetFacts facts) {
			if (nonNull(AgentRequestRule.this.initialParameters)) {
				AgentRequestRule.this.initialParameters.replace(FACTS, facts);
			}

			return isNull(expressionEvaluateBeforeForAll) ?
					evaluateBeforeForAll(facts) :
					(boolean) MVEL.executeExpression(expressionEvaluateBeforeForAll,
							AgentRequestRule.this.initialParameters);
		}

		@Override
		public void executeRule(final RuleSetFacts facts) {
			final Collection<ACLMessage> informResults = facts.get(REQUEST_INFORM_RESULTS_MESSAGES);
			final Collection<ACLMessage> failureResults = facts.get(REQUEST_FAILURE_RESULTS_MESSAGES);
			if (nonNull(AgentRequestRule.this.initialParameters)) {
				AgentRequestRule.this.initialParameters.replace(FACTS, facts);
			}

			if (isNull(expressionHandleAllResults)) {
				handleAllResults(informResults, failureResults, facts);
			} else {
				AgentRequestRule.this.initialParameters.put(INFORM_RESULTS, informResults);
				AgentRequestRule.this.initialParameters.put(FAILURE_RESULTS, failureResults);
				MVEL.executeExpression(expressionHandleAllResults, AgentRequestRule.this.initialParameters);
				AgentRequestRule.this.initialParameters.remove(INFORM_RESULTS);
				AgentRequestRule.this.initialParameters.remove(FAILURE_RESULTS);
			}
		}

		@Override
		public AgentRuleDescription initializeRuleDescription() {
			return new AgentRuleDescription(AgentRequestRule.this.ruleType, REQUEST_HANDLE_ALL_RESULTS_STEP,
					format("%s - handle all messages", AgentRequestRule.this.name),
					"rule that handles case when all INFORM and FAILURE messages are received");
		}

		@Override
		public AgentRule copy() {
			return new HandleAllResponsesRule();
		}
	}

}
