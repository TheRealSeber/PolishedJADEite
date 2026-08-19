package org.jrba.rulesengine.rule.template;

import static jade.lang.acl.ACLMessage.SUBSCRIBE;
import static java.lang.String.format;
import static java.util.Objects.isNull;
import static java.util.Objects.nonNull;
import static org.jrba.rulesengine.constants.FactTypeConstants.RULE_SET_IDX;
import static org.jrba.rulesengine.constants.FactTypeConstants.SUBSCRIPTION_ADDED_AGENTS;
import static org.jrba.rulesengine.constants.FactTypeConstants.SUBSCRIPTION_CREATE_MESSAGE;
import static org.jrba.rulesengine.constants.FactTypeConstants.SUBSCRIPTION_REMOVED_AGENTS;
import static org.jrba.rulesengine.constants.MVELParameterConstants.ADDED_AGENTS;
import static org.jrba.rulesengine.constants.MVELParameterConstants.FACTS;
import static org.jrba.rulesengine.constants.MVELParameterConstants.REMOVED_AGENTS;
import static org.jrba.rulesengine.constants.RuleTypeConstants.DEFAULT_SUBSCRIPTION_RULE;
import static org.jrba.rulesengine.types.rulesteptype.RuleStepTypeEnum.SUBSCRIPTION_CREATE_STEP;
import static org.jrba.rulesengine.types.rulesteptype.RuleStepTypeEnum.SUBSCRIPTION_HANDLE_AGENTS_RESPONSE_STEP;
import static org.jrba.rulesengine.types.ruletype.AgentRuleTypeEnum.SUBSCRIPTION;

import java.io.Serializable;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import org.jrba.agentmodel.domain.node.AgentNode;
import org.jrba.agentmodel.domain.props.AgentProps;
import org.jrba.rulesengine.RulesController;
import org.jrba.rulesengine.rest.domain.SubscriptionRuleRest;
import org.jrba.rulesengine.rule.AgentBasicRule;
import org.jrba.rulesengine.rule.AgentRule;
import org.jrba.rulesengine.rule.AgentRuleDescription;
import org.jrba.rulesengine.ruleset.RuleSetFacts;
import org.jrba.utils.messages.MessageBuilder;
import org.mvel2.MVEL;

import jade.core.AID;
import jade.lang.acl.ACLMessage;
import lombok.Getter;

/**
 * Abstract class defining structure of a rule which handles default Subscription behaviour.
 *
 * @param <E> type of node connected to the Agent
 * @param <T> type of properties of Agent
 */
@Getter
public class AgentSubscriptionRule<T extends AgentProps, E extends AgentNode<T>> extends AgentBasicRule<T, E> {

	protected Serializable expressionCreateSubscriptionMessage;
	protected Serializable expressionHandleRemovedAgents;
	protected Serializable expressionHandleAddedAgents;

	/**
	 * Copy constructor.
	 *
	 * @param rule rule that is to be copied
	 */
	public AgentSubscriptionRule(final AgentSubscriptionRule<T, E> rule) {
		super(rule);
		this.expressionCreateSubscriptionMessage = rule.getExpressionCreateSubscriptionMessage();
		this.expressionHandleRemovedAgents = rule.getExpressionHandleRemovedAgents();
		this.expressionHandleAddedAgents = rule.getExpressionHandleAddedAgents();
	}

	/**
	 * Constructor
	 *
	 * @param controller rules controller connected to the agent
	 */
	protected AgentSubscriptionRule(final RulesController<T, E> controller) {
		super(controller);
		initializeSteps();
	}

	/**
	 * Constructor
	 *
	 * @param ruleRest rest representation of agent rule
	 */
	public AgentSubscriptionRule(final SubscriptionRuleRest ruleRest) {
		super(ruleRest);
		if (nonNull(ruleRest.getCreateSubscriptionMessage())) {
			this.expressionCreateSubscriptionMessage = MVEL.compileExpression(
					imports + " " + ruleRest.getCreateSubscriptionMessage());
		}
		if (nonNull(ruleRest.getHandleAddedAgents())) {
			this.expressionHandleAddedAgents = MVEL.compileExpression(
					imports + " " + ruleRest.getHandleAddedAgents());
		}
		if (nonNull(ruleRest.getHandleRemovedAgents())) {
			this.expressionHandleRemovedAgents = MVEL.compileExpression(
					imports + " " + ruleRest.getHandleRemovedAgents());
		}
		initializeSteps();
	}

	/**
	 * Method assigns a list of subscription steps.
	 */
	public void initializeSteps() {
		stepRules = new ArrayList<>(List.of(new CreateSubscriptionRule(), new HandleDFInformMessage()));
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
		return SUBSCRIPTION.getType();
	}

	/**
	 * Method executed when subscription message is to be created.
	 *
	 * @param facts facts with additional parameters
	 * @return initialized subscription message
	 */
	protected ACLMessage createSubscriptionMessage(final RuleSetFacts facts) {
		return MessageBuilder.builder(facts.get(RULE_SET_IDX).toString(), SUBSCRIBE).build();
	}

	/**
	 * Method handles removing agents which deregistered their service.
	 *
	 * @param removedAgents map of agents, which removed their services from DF
	 */
	protected void handleRemovedAgents(final Map<AID, Boolean> removedAgents) {
		// TO BE OVERRIDDEN BY USER
	}

	/**
	 * Method handles adding new agents which registered their service.
	 *
	 * @param addedAgents map of agents, which added their services to DF
	 */
	protected void handleAddedAgents(final Map<AID, Boolean> addedAgents) {
		// TO BE OVERRIDDEN BY USER
	}

	@Override
	public AgentRuleDescription initializeRuleDescription() {
		return new AgentRuleDescription(DEFAULT_SUBSCRIPTION_RULE,
				"default subscription rule",
				"default implementation of a rule that handle (de-)registration of new agent services");
	}

	@Override
	public AgentRule copy() {
		return new AgentSubscriptionRule<>(this);
	}

	// RULE EXECUTED WHEN SUBSCRIPTION MESSAGE IS TO BE CREATED
	class CreateSubscriptionRule extends AgentBasicRule<T, E> {

		public CreateSubscriptionRule() {
			super(AgentSubscriptionRule.this.controller);
			this.isRuleStep = true;
		}

		@Override
		public void executeRule(final RuleSetFacts facts) {
			if (nonNull(AgentSubscriptionRule.this.initialParameters)) {
				AgentSubscriptionRule.this.initialParameters.replace(FACTS, facts);
			}

			final ACLMessage cfp = isNull(expressionCreateSubscriptionMessage) ?
					createSubscriptionMessage(facts) :
					(ACLMessage) MVEL.executeExpression(expressionCreateSubscriptionMessage,
							AgentSubscriptionRule.this.initialParameters);
			facts.put(SUBSCRIPTION_CREATE_MESSAGE, cfp);
		}

		@Override
		public AgentRuleDescription initializeRuleDescription() {
			return new AgentRuleDescription(AgentSubscriptionRule.this.ruleType,
					SUBSCRIPTION_CREATE_STEP,
					format("%s - create subscription message", AgentSubscriptionRule.this.name),
					"when agent initiate DF subscription, it creates subscription message");
		}

		@Override
		public AgentRule copy() {
			return new CreateSubscriptionRule();
		}
	}

	// RULE EXECUTED WHEN RESPONSE IS RECEIVED FROM DF
	class HandleDFInformMessage extends AgentBasicRule<T, E> {

		public HandleDFInformMessage() {
			super(AgentSubscriptionRule.this.controller);
			this.isRuleStep = true;
		}

		@Override
		public void executeRule(final RuleSetFacts facts) {
			final Map<AID, Boolean> addedAgents = facts.get(SUBSCRIPTION_ADDED_AGENTS);
			final Map<AID, Boolean> removedAgents = facts.get(SUBSCRIPTION_REMOVED_AGENTS);
			if (nonNull(AgentSubscriptionRule.this.initialParameters)) {
				AgentSubscriptionRule.this.initialParameters.replace(FACTS, facts);
			}

			if (!addedAgents.isEmpty()) {
				if (isNull(expressionHandleAddedAgents)) {
					handleAddedAgents(addedAgents);
				} else {
					AgentSubscriptionRule.this.initialParameters.put(ADDED_AGENTS, addedAgents);
					MVEL.executeExpression(expressionHandleAddedAgents, AgentSubscriptionRule.this.initialParameters);
					AgentSubscriptionRule.this.initialParameters.remove(ADDED_AGENTS);
				}
			}
			if (!removedAgents.isEmpty()) {
				if (isNull(expressionHandleRemovedAgents)) {
					handleRemovedAgents(removedAgents);
				} else {
					AgentSubscriptionRule.this.initialParameters.put(REMOVED_AGENTS, removedAgents);
					MVEL.executeExpression(expressionHandleRemovedAgents, AgentSubscriptionRule.this.initialParameters);
					AgentSubscriptionRule.this.initialParameters.remove(REMOVED_AGENTS);
				}
			}
		}

		@Override
		public AgentRuleDescription initializeRuleDescription() {
			return new AgentRuleDescription(AgentSubscriptionRule.this.ruleType,
					SUBSCRIPTION_HANDLE_AGENTS_RESPONSE_STEP,
					format("%s - handle changes in subscribed service", AgentSubscriptionRule.this.name),
					"when DF sends information about changes in subscribed service, agent executes default"
							+ " handlers");
		}

		@Override
		public AgentRule copy() {
			return new HandleDFInformMessage();
		}
	}

}
