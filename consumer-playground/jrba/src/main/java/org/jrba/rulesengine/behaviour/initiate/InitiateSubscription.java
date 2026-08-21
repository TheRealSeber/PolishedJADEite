package org.jrba.rulesengine.behaviour.initiate;

import static java.util.Objects.isNull;
import static java.util.stream.Collectors.toMap;
import static org.jrba.rulesengine.constants.FactTypeConstants.RULE_SET_IDX;
import static org.jrba.rulesengine.constants.FactTypeConstants.RULE_STEP;
import static org.jrba.rulesengine.constants.FactTypeConstants.RULE_TYPE;
import static org.jrba.rulesengine.constants.FactTypeConstants.SUBSCRIPTION_ADDED_AGENTS;
import static org.jrba.rulesengine.constants.FactTypeConstants.SUBSCRIPTION_CREATE_MESSAGE;
import static org.jrba.rulesengine.constants.FactTypeConstants.SUBSCRIPTION_REMOVED_AGENTS;
import static org.jrba.rulesengine.types.rulesteptype.RuleStepTypeEnum.SUBSCRIPTION_CREATE_STEP;
import static org.jrba.rulesengine.types.rulesteptype.RuleStepTypeEnum.SUBSCRIPTION_HANDLE_AGENTS_RESPONSE_STEP;
import static org.jrba.utils.mapper.FactsMapper.mapToRuleSetFacts;
import static org.jrba.utils.yellowpages.YellowPagesRegister.decodeSubscription;

import java.util.Map;
import java.util.function.ToIntFunction;

import org.jeasy.rules.api.Facts;
import org.jrba.rulesengine.RulesController;
import org.jrba.rulesengine.ruleset.RuleSetFacts;

import jade.core.AID;
import jade.core.Agent;
import jade.lang.acl.ACLMessage;
import jade.proto.SubscriptionInitiator;

/**
 * Abstract behaviour providing template initiating Subscription protocol handled with rules
 */
public class InitiateSubscription extends SubscriptionInitiator {

	protected final ToIntFunction<Facts> selectRuleSet;
	protected final RuleSetFacts facts;

	/**
	 * Controller responsible for rules triggering.
	 */
	protected RulesController<?, ?> controller;

	private InitiateSubscription(final Agent agent, final RuleSetFacts facts,
			final RulesController<?, ?> controller, final ToIntFunction<Facts> selectRuleSet) {
		super(agent, facts.get(SUBSCRIPTION_CREATE_MESSAGE));
		this.facts = facts;
		this.controller = controller;
		this.selectRuleSet = isNull(selectRuleSet) ?
				o -> controller.getLatestLongTermRuleSetIdx().get() :
				selectRuleSet;
	}

	/**
	 * Method creates behaviour
	 *
	 * @param agent      agent executing the behaviour
	 * @param facts      facts under which the Subscription message is to be created
	 * @param ruleType   type of the rule that handles Subscription execution
	 * @param controller rules controller
	 * @return InitiateSubscription
	 */
	public static InitiateSubscription create(final Agent agent, final RuleSetFacts facts, final String ruleType,
			final RulesController<?, ?> controller) {
		final RuleSetFacts methodFacts = mapToRuleSetFacts(facts);
		methodFacts.put(RULE_TYPE, ruleType);
		methodFacts.put(RULE_STEP, SUBSCRIPTION_CREATE_STEP.getType());
		controller.fire(methodFacts);

		return new InitiateSubscription(agent, methodFacts, controller, null);
	}

	/**
	 * Method creates behaviour
	 *
	 * @param agent         agent executing the behaviour
	 * @param facts         facts under which the Subscription message is to be created
	 * @param ruleType      type of the rule that handles Subscription execution
	 * @param controller    rules controller
	 * @param selectRuleSet predicate specifying how the rule set of the given behaviour should be selected
	 * @return InitiateSubscription
	 */
	public static InitiateSubscription create(final Agent agent, final RuleSetFacts facts, final String ruleType,
			final RulesController<?, ?> controller, final ToIntFunction<Facts> selectRuleSet) {
		final RuleSetFacts methodFacts = mapToRuleSetFacts(facts);
		methodFacts.put(RULE_TYPE, ruleType);
		methodFacts.put(RULE_STEP, SUBSCRIPTION_CREATE_STEP.getType());
		controller.fire(methodFacts);

		return new InitiateSubscription(agent, methodFacts, controller, selectRuleSet);
	}

	/**
	 * Method is triggered when agents register/deregister their services in DF.
	 * It groups the agents into 2 lists based on registration state
	 * (i.e. agents that registered their service and agents that deregistered their service).
	 * Then, it applies predefined handling methods.
	 *
	 * @param inform retrieved notification
	 */
	@Override
	protected void handleInform(final ACLMessage inform) {
		final Map<AID, Boolean> announcedAgents = decodeSubscription(inform);

		final Map<AID, Boolean> addedAgents = announcedAgents.entrySet().stream()
				.filter(Map.Entry::getValue)
				.collect(toMap(Map.Entry::getKey, aidBooleanEntry -> true));

		final Map<AID, Boolean> removedAgents = announcedAgents.entrySet().stream()
				.filter(entry -> !entry.getValue())
				.collect(toMap(Map.Entry::getKey, aidBooleanEntry -> false));

		if (!addedAgents.isEmpty() || !removedAgents.isEmpty()) {
			facts.put(RULE_STEP, SUBSCRIPTION_HANDLE_AGENTS_RESPONSE_STEP.getType());
			facts.put(SUBSCRIPTION_ADDED_AGENTS, addedAgents);
			facts.put(SUBSCRIPTION_REMOVED_AGENTS, removedAgents);

			final int ruleSetIdx = selectRuleSet.applyAsInt(facts);
			facts.put(RULE_SET_IDX, ruleSetIdx);

			controller.fire(facts);
			postProcessSubscriptionResponse(facts);
		}
	}

	/**
	 * Method can be optionally overridden in order to perform facts-based actions after handling subscription response
	 * message.
	 *
	 * @param facts facts with additional parameters
	 */
	protected void postProcessSubscriptionResponse(final RuleSetFacts facts) {
		// to be overridden if necessary
	}
}
