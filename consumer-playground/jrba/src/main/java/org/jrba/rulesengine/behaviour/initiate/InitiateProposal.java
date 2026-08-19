package org.jrba.rulesengine.behaviour.initiate;

import static org.jrba.utils.mapper.FactsMapper.mapToRuleSetFacts;
import static org.jrba.rulesengine.constants.FactTypeConstants.PROPOSAL_ACCEPT_MESSAGE;
import static org.jrba.rulesengine.constants.FactTypeConstants.PROPOSAL_CREATE_MESSAGE;
import static org.jrba.rulesengine.constants.FactTypeConstants.PROPOSAL_REJECT_MESSAGE;
import static org.jrba.rulesengine.constants.FactTypeConstants.RULE_STEP;
import static org.jrba.rulesengine.constants.FactTypeConstants.RULE_TYPE;
import static org.jrba.rulesengine.types.rulesteptype.RuleStepTypeEnum.PROPOSAL_CREATE_STEP;
import static org.jrba.rulesengine.types.rulesteptype.RuleStepTypeEnum.PROPOSAL_HANDLE_ACCEPT_STEP;
import static org.jrba.rulesengine.types.rulesteptype.RuleStepTypeEnum.PROPOSAL_HANDLE_REJECT_STEP;

import org.jrba.rulesengine.RulesController;
import org.jrba.rulesengine.ruleset.RuleSetFacts;

import jade.core.Agent;
import jade.lang.acl.ACLMessage;
import jade.proto.ProposeInitiator;

/**
 * Abstract behaviour providing template initiating Proposal protocol handled with rules.
 */
public class InitiateProposal extends ProposeInitiator {

	protected RuleSetFacts facts;
	protected RulesController<?, ?> controller;

	private InitiateProposal(final Agent agent, final RuleSetFacts facts, final RulesController<?, ?> controller) {
		super(agent, facts.get(PROPOSAL_CREATE_MESSAGE));

		this.controller = controller;
		this.facts = facts;
	}

	/**
	 * Method creates behaviour
	 *
	 * @param agent      agent executing the behaviour
	 * @param facts      facts under which the Proposal message is to be created
	 * @param ruleType   type of the rule that handles Proposal execution
	 * @param controller rules controller
	 * @return InitiateProposal
	 */
	public static InitiateProposal create(final Agent agent, final RuleSetFacts facts, final String ruleType,
			final RulesController<?, ?> controller) {
		final RuleSetFacts methodFacts = mapToRuleSetFacts(facts);
		methodFacts.put(RULE_TYPE, ruleType);
		methodFacts.put(RULE_STEP, PROPOSAL_CREATE_STEP.getType());
		controller.fire(methodFacts);

		return new InitiateProposal(agent, methodFacts, controller);
	}

	/**
	 * Method handles ACCEPT_PROPOSAL message retrieved from the agent.
	 */
	@Override
	protected void handleAcceptProposal(final ACLMessage accept) {
		facts.put(RULE_STEP, PROPOSAL_HANDLE_ACCEPT_STEP.getType());
		facts.put(PROPOSAL_ACCEPT_MESSAGE, accept);
		controller.fire(facts);
		postProcessAcceptProposal(facts);
	}

	/**
	 * Method handles REJECT_PROPOSAL message retrieved from the agent.
	 */
	@Override
	protected void handleRejectProposal(final ACLMessage reject) {
		facts.put(RULE_STEP, PROPOSAL_HANDLE_REJECT_STEP.getType());
		facts.put(PROPOSAL_REJECT_MESSAGE, reject);
		controller.fire(facts);
		postProcessRejectProposal(facts);
	}

	/**
	 * Method can be optionally overridden in order to perform facts-based actions after handling acceptance message.
	 *
	 * @param facts facts with additional parameters
	 */
	protected void postProcessAcceptProposal(final RuleSetFacts facts) {
		// to be overridden if necessary
	}

	/**
	 * Method can be optionally overridden in order to perform facts-based actions after handling rejection message.
	 *
	 * @param facts facts with additional parameters
	 */
	protected void postProcessRejectProposal(final RuleSetFacts facts) {
		// to be overridden if necessary
	}

}
