package org.jrba.rulesengine.behaviour.initiate;

import static jade.lang.acl.ACLMessage.PROPOSE;
import static java.util.Objects.isNull;
import static org.jrba.utils.mapper.FactsMapper.mapToRuleSetFacts;
import static org.jrba.rulesengine.constants.FactTypeConstants.CFP_BEST_MESSAGE;
import static org.jrba.rulesengine.constants.FactTypeConstants.CFP_CREATE_MESSAGE;
import static org.jrba.rulesengine.constants.FactTypeConstants.CFP_NEW_PROPOSAL;
import static org.jrba.rulesengine.constants.FactTypeConstants.CFP_RECEIVED_PROPOSALS;
import static org.jrba.rulesengine.constants.FactTypeConstants.CFP_REJECT_MESSAGE;
import static org.jrba.rulesengine.constants.FactTypeConstants.CFP_RESULT;
import static org.jrba.rulesengine.constants.FactTypeConstants.RULE_STEP;
import static org.jrba.rulesengine.constants.FactTypeConstants.RULE_TYPE;
import static org.jrba.rulesengine.types.rulesteptype.RuleStepTypeEnum.CFP_COMPARE_MESSAGES_STEP;
import static org.jrba.rulesengine.types.rulesteptype.RuleStepTypeEnum.CFP_CREATE_STEP;
import static org.jrba.rulesengine.types.rulesteptype.RuleStepTypeEnum.CFP_HANDLE_NO_AVAILABLE_AGENTS_STEP;
import static org.jrba.rulesengine.types.rulesteptype.RuleStepTypeEnum.CFP_HANDLE_NO_RESPONSES_STEP;
import static org.jrba.rulesengine.types.rulesteptype.RuleStepTypeEnum.CFP_HANDLE_REJECT_PROPOSAL_STEP;
import static org.jrba.rulesengine.types.rulesteptype.RuleStepTypeEnum.CFP_HANDLE_SELECTED_PROPOSAL_STEP;
import static org.jrba.utils.messages.MessageReader.readForPerformative;

import java.util.Vector;

import org.jrba.rulesengine.RulesController;
import org.jrba.rulesengine.ruleset.RuleSetFacts;

import jade.core.Agent;
import jade.lang.acl.ACLMessage;
import jade.proto.ContractNetInitiator;

/**
 * Abstract behaviour providing template initiating Call For Proposal protocol handled with rules
 */
public class InitiateCallForProposal extends ContractNetInitiator {

	protected ACLMessage bestProposal;
	protected RuleSetFacts facts;
	protected RulesController<?, ?> controller;

	private InitiateCallForProposal(final Agent agent, final RuleSetFacts facts,
			final RulesController<?, ?> controller) {
		super(agent, facts.get(CFP_CREATE_MESSAGE));

		this.controller = controller;
		this.facts = facts;
	}

	/**
	 * Method creates behaviour
	 *
	 * @param agent      agent executing the behaviour
	 * @param facts      facts under which the CFP message is to be created
	 * @param ruleType   type of the rule that handles CFP execution
	 * @param controller rules controller
	 * @return InitiateCallForProposal
	 */
	public static InitiateCallForProposal create(final Agent agent, final RuleSetFacts facts, final String ruleType,
			final RulesController<?, ?> controller) {
		final RuleSetFacts methodFacts = mapToRuleSetFacts(facts);
		methodFacts.put(RULE_TYPE, ruleType);
		methodFacts.put(RULE_STEP, CFP_CREATE_STEP.getType());
		controller.fire(methodFacts);

		return new InitiateCallForProposal(agent, methodFacts, controller);
	}

	/**
	 * Generic way of handling PROPOSE response.
	 * Method verifies if newly received proposal is better than the current best one and, upon that, updates
	 * the information regarding the best proposal and executes handler for rejected proposal.
	 *
	 * @param propose     received proposal
	 * @param acceptances vector containing accept proposal message sent back to the chosen server (not used)
	 */
	@Override
	protected void handlePropose(final ACLMessage propose, final Vector acceptances) {
		if (isNull(bestProposal)) {
			bestProposal = propose;
			facts.put(CFP_BEST_MESSAGE, bestProposal);
			return;
		}

		facts.put(RULE_STEP, CFP_COMPARE_MESSAGES_STEP.getType());
		facts.put(CFP_BEST_MESSAGE, bestProposal);
		facts.put(CFP_NEW_PROPOSAL, propose);
		controller.fire(facts);

		final int comparisonResult = facts.get(CFP_RESULT);
		final ACLMessage proposalToReject = comparisonResult < 0 ? (ACLMessage) bestProposal.clone() : propose;

		facts.put(RULE_STEP, CFP_HANDLE_REJECT_PROPOSAL_STEP.getType());
		facts.put(CFP_REJECT_MESSAGE, proposalToReject);
		controller.fire(facts);

		if (comparisonResult < 0) {
			bestProposal = propose;
		}
		postProcessProposal(facts);
	}

	/**
	 * Generic way of handling all received responses.
	 * Method handles 3 cases:
	 * <p> 1) case when no responses were retrieved </p>
	 * <p> 2) case when all agents refused to provide a given service </p>
	 * <p> 3) case when there exists best proposal message </p>
	 * <p> In order to handle the aforementioned cases the method uses specific rule steps and fires agent rule set. </p>
	 *
	 * @param responses   retrieved responses
	 * @param acceptances vector containing accept proposal message sent back to the chosen server (not used)
	 */
	@Override
	protected void handleAllResponses(final Vector responses, final Vector acceptances) {
		if (responses.isEmpty()) {
			facts.put(RULE_STEP, CFP_HANDLE_NO_RESPONSES_STEP.getType());
		} else if (isNull(bestProposal)) {
			facts.put(RULE_STEP, CFP_HANDLE_NO_AVAILABLE_AGENTS_STEP.getType());
		} else {
			facts.put(CFP_BEST_MESSAGE, bestProposal);
			facts.put(CFP_RECEIVED_PROPOSALS, readForPerformative(responses, PROPOSE));
			facts.put(RULE_STEP, CFP_HANDLE_SELECTED_PROPOSAL_STEP.getType());
		}
		controller.fire(facts);
		postProcessAllResponses(facts);
		myAgent.removeBehaviour(this);
	}

	/**
	 * Method can be optionally overridden in order to perform facts-based actions after handling all responses.
	 *
	 * @param facts facts with additional parameters
	 */
	protected void postProcessAllResponses(final RuleSetFacts facts) {
		// to be overridden if necessary
	}

	/**
	 * Method can be optionally overridden in order to perform facts-based actions after handling single proposal message.
	 *
	 * @param facts facts with additional parameters
	 */
	protected void postProcessProposal(final RuleSetFacts facts) {
		// to be overridden if necessary
	}

}
