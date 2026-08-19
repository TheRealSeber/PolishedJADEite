package org.jrba.rulesengine.behaviour.initiate;

import static jade.lang.acl.ACLMessage.FAILURE;
import static jade.lang.acl.ACLMessage.INFORM;
import static org.jrba.utils.mapper.FactsMapper.mapToRuleSetFacts;
import static org.jrba.rulesengine.constants.FactTypeConstants.REQUEST_CREATE_MESSAGE;
import static org.jrba.rulesengine.constants.FactTypeConstants.REQUEST_FAILURE_MESSAGE;
import static org.jrba.rulesengine.constants.FactTypeConstants.REQUEST_FAILURE_RESULTS_MESSAGES;
import static org.jrba.rulesengine.constants.FactTypeConstants.REQUEST_INFORM_MESSAGE;
import static org.jrba.rulesengine.constants.FactTypeConstants.REQUEST_INFORM_RESULTS_MESSAGES;
import static org.jrba.rulesengine.constants.FactTypeConstants.REQUEST_REFUSE_MESSAGE;
import static org.jrba.rulesengine.constants.FactTypeConstants.RULE_STEP;
import static org.jrba.rulesengine.constants.FactTypeConstants.RULE_TYPE;
import static org.jrba.rulesengine.types.rulesteptype.RuleStepTypeEnum.REQUEST_CREATE_STEP;
import static org.jrba.rulesengine.types.rulesteptype.RuleStepTypeEnum.REQUEST_HANDLE_ALL_RESULTS_STEP;
import static org.jrba.rulesengine.types.rulesteptype.RuleStepTypeEnum.REQUEST_HANDLE_FAILURE_STEP;
import static org.jrba.rulesengine.types.rulesteptype.RuleStepTypeEnum.REQUEST_HANDLE_INFORM_STEP;
import static org.jrba.rulesengine.types.rulesteptype.RuleStepTypeEnum.REQUEST_HANDLE_REFUSE_STEP;
import static org.jrba.utils.messages.MessageReader.readForPerformative;

import java.util.Vector;

import org.jrba.rulesengine.RulesController;
import org.jrba.rulesengine.ruleset.RuleSetFacts;

import jade.core.Agent;
import jade.lang.acl.ACLMessage;
import jade.proto.AchieveREInitiator;

/**
 * Abstract behaviour providing template initiating Request protocol handled with rules
 */
public class InitiateRequest extends AchieveREInitiator {

	protected RuleSetFacts facts;
	protected RulesController<?, ?> controller;

	private InitiateRequest(final Agent agent, final RuleSetFacts facts, final RulesController<?, ?> controller) {
		super(agent, facts.get(REQUEST_CREATE_MESSAGE));

		this.controller = controller;
		this.facts = facts;
	}

	/**
	 * Method creates behaviour
	 *
	 * @param agent      agent executing the behaviour
	 * @param facts      facts under which the Request message is to be created
	 * @param ruleType   type of the rule that handles Request execution
	 * @param controller rules controller
	 * @return InitiateRequest
	 */
	public static InitiateRequest create(final Agent agent, final RuleSetFacts facts, final String ruleType,
			final RulesController<?, ?> controller) {
		final RuleSetFacts methodFacts = mapToRuleSetFacts(facts);
		methodFacts.put(RULE_TYPE, ruleType);
		methodFacts.put(RULE_STEP, REQUEST_CREATE_STEP.getType());
		controller.fire(methodFacts);

		return new InitiateRequest(agent, methodFacts, controller);
	}

	/**
	 * Method handles INFORM message retrieved from the agent.
	 */
	@Override
	protected void handleInform(final ACLMessage inform) {
		facts.put(RULE_STEP, REQUEST_HANDLE_INFORM_STEP.getType());
		facts.put(REQUEST_INFORM_MESSAGE, inform);
		controller.fire(facts);
		postProcessInform(facts);
	}

	/**
	 * Method handles REFUSE message retrieved from the agent.
	 */
	@Override
	protected void handleRefuse(final ACLMessage refuse) {
		facts.put(RULE_STEP, REQUEST_HANDLE_REFUSE_STEP.getType());
		facts.put(REQUEST_REFUSE_MESSAGE, refuse);
		controller.fire(facts);
		postProcessRefuse(facts);
	}

	/**
	 * Method handles FAILURE message retrieved from the agent.
	 */
	@Override
	protected void handleFailure(final ACLMessage failure) {
		facts.put(RULE_STEP, REQUEST_HANDLE_FAILURE_STEP.getType());
		facts.put(REQUEST_FAILURE_MESSAGE, failure);
		controller.fire(facts);
		postProcessFailure(facts);
	}

	@Override
	protected void handleAllResultNotifications(final Vector resultNotifications) {
		facts.put(RULE_STEP, REQUEST_HANDLE_ALL_RESULTS_STEP.getType());
		facts.put(REQUEST_INFORM_RESULTS_MESSAGES, readForPerformative(resultNotifications, INFORM));
		facts.put(REQUEST_FAILURE_RESULTS_MESSAGES, readForPerformative(resultNotifications, FAILURE));
		controller.fire(facts);
		postProcessFailure(facts);
	}

	/**
	 * Method can be optionally overridden in order to perform facts-based actions after handling inform message.
	 *
	 * @param facts facts with additional parameters
	 */
	protected void postProcessInform(final RuleSetFacts facts) {
		// to be overridden if necessary
	}

	/**
	 * Method can be optionally overridden in order to perform facts-based actions after handling refuse message.
	 *
	 * @param facts facts with additional parameters
	 */
	protected void postProcessRefuse(final RuleSetFacts facts) {
		// to be overridden if necessary
	}

	/**
	 * Method can be optionally overridden in order to perform facts-based actions after handling failure message.
	 *
	 * @param facts facts with additional parameters
	 */
	protected void postProcessFailure(final RuleSetFacts facts) {
		// to be overridden if necessary
	}
}
