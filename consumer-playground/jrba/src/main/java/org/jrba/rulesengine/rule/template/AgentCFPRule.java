package org.jrba.rulesengine.rule.template;

import static java.lang.Integer.parseInt;
import static java.lang.String.format;
import static java.util.Objects.isNull;
import static java.util.Objects.nonNull;
import static org.jrba.rulesengine.constants.FactTypeConstants.CFP_BEST_MESSAGE;
import static org.jrba.rulesengine.constants.FactTypeConstants.CFP_CREATE_MESSAGE;
import static org.jrba.rulesengine.constants.FactTypeConstants.CFP_NEW_PROPOSAL;
import static org.jrba.rulesengine.constants.FactTypeConstants.CFP_RECEIVED_PROPOSALS;
import static org.jrba.rulesengine.constants.FactTypeConstants.CFP_REJECT_MESSAGE;
import static org.jrba.rulesengine.constants.FactTypeConstants.CFP_RESULT;
import static org.jrba.rulesengine.constants.FactTypeConstants.RULE_SET_IDX;
import static org.jrba.rulesengine.constants.MVELParameterConstants.ALL_PROPOSALS;
import static org.jrba.rulesengine.constants.MVELParameterConstants.BEST_PROPOSAL;
import static org.jrba.rulesengine.constants.MVELParameterConstants.FACTS;
import static org.jrba.rulesengine.constants.MVELParameterConstants.NEW_PROPOSAL;
import static org.jrba.rulesengine.constants.MVELParameterConstants.PROPOSAL_TO_REJECT;
import static org.jrba.rulesengine.constants.RuleTypeConstants.DEFAULT_CFP_RULE;
import static org.jrba.rulesengine.types.rulesteptype.RuleStepTypeEnum.CFP_COMPARE_MESSAGES_STEP;
import static org.jrba.rulesengine.types.rulesteptype.RuleStepTypeEnum.CFP_CREATE_STEP;
import static org.jrba.rulesengine.types.rulesteptype.RuleStepTypeEnum.CFP_HANDLE_NO_AVAILABLE_AGENTS_STEP;
import static org.jrba.rulesengine.types.rulesteptype.RuleStepTypeEnum.CFP_HANDLE_NO_RESPONSES_STEP;
import static org.jrba.rulesengine.types.rulesteptype.RuleStepTypeEnum.CFP_HANDLE_REJECT_PROPOSAL_STEP;
import static org.jrba.rulesengine.types.rulesteptype.RuleStepTypeEnum.CFP_HANDLE_SELECTED_PROPOSAL_STEP;
import static org.jrba.rulesengine.types.ruletype.AgentRuleTypeEnum.CFP;

import java.io.Serializable;
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;

import org.jrba.agentmodel.domain.node.AgentNode;
import org.jrba.agentmodel.domain.props.AgentProps;
import org.jrba.rulesengine.RulesController;
import org.jrba.rulesengine.rest.domain.CallForProposalRuleRest;
import org.jrba.rulesengine.rule.AgentBasicRule;
import org.jrba.rulesengine.rule.AgentRule;
import org.jrba.rulesengine.rule.AgentRuleDescription;
import org.jrba.rulesengine.ruleset.RuleSetFacts;
import org.jrba.utils.messages.MessageBuilder;
import org.mvel2.MVEL;

import jade.lang.acl.ACLMessage;
import lombok.Getter;

/**
 * Abstract class defining structure of a rule which handles default Call For Proposal initiator behaviour.
 *
 * @param <E> type of node connected to the Agent
 * @param <T> type of properties of Agent
 */
@Getter
public class AgentCFPRule<T extends AgentProps, E extends AgentNode<T>> extends AgentBasicRule<T, E> {

	protected Serializable expressionCreateCFP;
	protected Serializable expressionCompareProposals;
	protected Serializable expressionHandleRejectProposal;
	protected Serializable expressionHandleNoResponses;
	protected Serializable expressionHandleNoProposals;
	protected Serializable expressionHandleProposals;

	/**
	 * Copy constructor.
	 *
	 * @param rule rule that is to be copied
	 */
	public AgentCFPRule(final AgentCFPRule<T, E> rule) {
		super(rule);
		this.expressionCreateCFP = rule.getExpressionCreateCFP();
		this.expressionCompareProposals = rule.getExpressionCompareProposals();
		this.expressionHandleRejectProposal = rule.getExpressionHandleRejectProposal();
		this.expressionHandleNoResponses = rule.getExpressionHandleNoResponses();
		this.expressionHandleNoProposals = rule.getExpressionHandleNoProposals();
		this.expressionHandleProposals = rule.getExpressionHandleProposals();
	}

	/**
	 * Constructor
	 *
	 * @param controller rules controller connected to the agent
	 */
	protected AgentCFPRule(final RulesController<T, E> controller) {
		super(controller);
		initializeSteps();
	}

	/**
	 * Constructor
	 *
	 * @param ruleRest rest representation of agent rule
	 */
	public AgentCFPRule(final CallForProposalRuleRest ruleRest) {
		super(ruleRest);
		if (nonNull(ruleRest.getCreateCFP())) {
			this.expressionCreateCFP = MVEL.compileExpression(
					imports + " " + ruleRest.getCreateCFP());
		}
		if (nonNull(ruleRest.getCompareProposals())) {
			this.expressionCompareProposals = MVEL.compileExpression(
					imports + " " + ruleRest.getCompareProposals());
		}
		if (nonNull(ruleRest.getHandleRejectProposal())) {
			this.expressionHandleRejectProposal = MVEL.compileExpression(
					imports + " " + ruleRest.getHandleRejectProposal());
		}
		if (nonNull(ruleRest.getHandleNoResponses())) {
			this.expressionHandleNoResponses = MVEL.compileExpression(
					imports + " " + ruleRest.getHandleNoResponses());
		}
		if (nonNull(ruleRest.getHandleNoProposals())) {
			this.expressionHandleNoProposals = MVEL.compileExpression(
					imports + " " + ruleRest.getHandleNoProposals());
		}
		if (nonNull(ruleRest.getHandleProposals())) {
			this.expressionHandleProposals = MVEL.compileExpression(
					imports + " " + ruleRest.getHandleProposals());
		}
		initializeSteps();
	}

	/**
	 * Method assigns a list of CFP steps.
	 */
	public void initializeSteps() {
		stepRules = new ArrayList<>(List.of(
				new CreateCFPRule(),
				new CompareCFPMessageRule(),
				new HandleRejectProposalRule(),
				new HandleNoProposalsRule(),
				new HandleNoResponsesRule(),
				new HandleProposalsRule()
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
		return CFP.getType();
	}

	/**
	 * Method executed when CFP message is to be created.
	 *
	 * @param facts facts used to create CFP message
	 * @return initialized CFP message
	 */
	protected ACLMessage createCFPMessage(final RuleSetFacts facts) {
		return MessageBuilder.builder(facts.get(RULE_SET_IDX).toString(), ACLMessage.CFP).build();
	}

	/**
	 * Method executed when new proposal is retrieved, and it is to be compared with existing best proposal.
	 *
	 * @param facts        facts with additional parameters to compare proposals
	 * @param bestProposal proposal which is currently the best
	 * @param newProposal  newly received proposal
	 * @return -1 - when newProposal is better,
	 * 0 - when proposals are equivalent,
	 * 1 - when bestProposal is better
	 */
	protected int compareProposals(final RuleSetFacts facts, final ACLMessage bestProposal,
			final ACLMessage newProposal) {
		return 0;
	}

	/**
	 * Method executed when a proposal is to be rejected.
	 *
	 * @param proposalToReject proposal, which is to be rejected.
	 * @param facts            facts with additional parameters to reject proposal
	 */
	protected void handleRejectProposal(final ACLMessage proposalToReject, final RuleSetFacts facts) {
		// TO BE OVERRIDDEN BY USER
	}

	/**
	 * Method executed when agent received 0 responses.
	 *
	 * @param facts facts with additional parameters
	 */
	protected void handleNoResponses(final RuleSetFacts facts) {
		// TO BE OVERRIDDEN BY USER
	}

	/**
	 * Method executed when agent received 0 proposals.
	 *
	 * @param facts facts with additional parameters
	 */
	protected void handleNoProposals(final RuleSetFacts facts) {
		// TO BE OVERRIDDEN BY USER
	}

	/**
	 * Method executed when agent received some proposals.
	 *
	 * @param facts        facts with additional parameters
	 * @param bestProposal proposal which is currently the best
	 * @param allProposals all proposals, which has been received
	 */
	protected void handleProposals(final ACLMessage bestProposal, final Collection<ACLMessage> allProposals,
			final RuleSetFacts facts) {
		// TO BE OVERRIDDEN BY USER
	}

	@Override
	public AgentRuleDescription initializeRuleDescription() {
		return new AgentRuleDescription(DEFAULT_CFP_RULE,
				"default Call For Proposal rule",
				"default implementation of a rule that executes Call For Proposal FIPA protocol");
	}

	@Override
	public AgentRule copy() {
		return new AgentCFPRule<>(this);
	}

	// RULE EXECUTED WHEN CFP MESSAGE IS TO BE CREATED
	class CreateCFPRule extends AgentBasicRule<T, E> {

		public CreateCFPRule() {
			super(AgentCFPRule.this.controller);
			this.isRuleStep = true;
		}

		@Override
		public void executeRule(final RuleSetFacts facts) {
			if (nonNull(AgentCFPRule.this.initialParameters)) {
				AgentCFPRule.this.initialParameters.replace(FACTS, facts);
			}

			final ACLMessage cfp = isNull(expressionCreateCFP) ? createCFPMessage(facts)
					: (ACLMessage) MVEL.executeExpression(expressionCreateCFP, AgentCFPRule.this.initialParameters);
			facts.put(CFP_CREATE_MESSAGE, cfp);
		}

		@Override
		public AgentRuleDescription initializeRuleDescription() {
			return new AgentRuleDescription(AgentCFPRule.this.ruleType, CFP_CREATE_STEP,
					format("%s - create CFP message", AgentCFPRule.this.name),
					"when agent initiate RMA lookup, it creates CFP");
		}

		@Override
		public AgentRule copy() {
			return new CreateCFPRule();
		}
	}

	// RULE EXECUTED WHEN TWO PROPOSALS ARE TO BE COMPARED
	class CompareCFPMessageRule extends AgentBasicRule<T, E> {

		public CompareCFPMessageRule() {
			super(AgentCFPRule.this.controller);
			this.isRuleStep = true;
		}

		@Override
		public void executeRule(final RuleSetFacts facts) {
			final ACLMessage bestProposal = facts.get(CFP_BEST_MESSAGE);
			final ACLMessage newProposal = facts.get(CFP_NEW_PROPOSAL);

			if (nonNull(AgentCFPRule.this.initialParameters)) {
				AgentCFPRule.this.initialParameters.replace(FACTS, facts);
			}
			int result;

			if (isNull(expressionCompareProposals)) {
				result = compareProposals(facts, bestProposal, newProposal);
			} else {
				AgentCFPRule.this.initialParameters.put(BEST_PROPOSAL, bestProposal);
				AgentCFPRule.this.initialParameters.put(NEW_PROPOSAL, newProposal);
				result = parseInt(MVEL.executeExpression(expressionCompareProposals,
						AgentCFPRule.this.initialParameters).toString());
				AgentCFPRule.this.initialParameters.remove(BEST_PROPOSAL);
				AgentCFPRule.this.initialParameters.remove(NEW_PROPOSAL);
			}
			facts.put(CFP_RESULT, result);
		}

		@Override
		public AgentRuleDescription initializeRuleDescription() {
			return new AgentRuleDescription(AgentCFPRule.this.ruleType, CFP_COMPARE_MESSAGES_STEP,
					format("%s - compare received proposal message", AgentCFPRule.this.name),
					"when agent receives new proposal message, it compares it with current best proposal");
		}

		@Override
		public AgentRule copy() {
			return new CompareCFPMessageRule();
		}
	}

	// RULE EXECUTED WHEN AGENT REJECTS PROPOSAL RESPONSE
	class HandleRejectProposalRule extends AgentBasicRule<T, E> {

		public HandleRejectProposalRule() {
			super(AgentCFPRule.this.controller);
			this.isRuleStep = true;
		}

		@Override
		public void executeRule(final RuleSetFacts facts) {
			final ACLMessage proposalToReject = facts.get(CFP_REJECT_MESSAGE);
			if (nonNull(AgentCFPRule.this.initialParameters)) {
				AgentCFPRule.this.initialParameters.replace(FACTS, facts);
			}

			if (isNull(expressionHandleRejectProposal)) {
				handleRejectProposal(proposalToReject, facts);
			} else {
				AgentCFPRule.this.initialParameters.put(PROPOSAL_TO_REJECT, proposalToReject);
				MVEL.executeExpression(expressionHandleRejectProposal, AgentCFPRule.this.initialParameters);
				AgentCFPRule.this.initialParameters.remove(PROPOSAL_TO_REJECT);
			}
		}

		@Override
		public AgentRuleDescription initializeRuleDescription() {
			return new AgentRuleDescription(AgentCFPRule.this.ruleType, CFP_HANDLE_REJECT_PROPOSAL_STEP,
					format("%s - reject received proposal", AgentCFPRule.this.name),
					"rule executed when received proposal is to be rejected");
		}

		@Override
		public AgentRule copy() {
			return new HandleRejectProposalRule();
		}
	}

	// RULE EXECUTED WHEN NO RESPONSES WERE RECEIVED
	class HandleNoResponsesRule extends AgentBasicRule<T, E> {

		public HandleNoResponsesRule() {
			super(AgentCFPRule.this.controller);
			this.isRuleStep = true;
		}

		@Override
		public void executeRule(final RuleSetFacts facts) {
			if (nonNull(AgentCFPRule.this.initialParameters)) {
				AgentCFPRule.this.initialParameters.replace(FACTS, facts);
			}

			if (isNull(expressionHandleNoResponses)) {
				handleNoResponses(facts);
			} else {
				MVEL.executeExpression(expressionHandleNoResponses, AgentCFPRule.this.initialParameters);
			}
		}

		@Override
		public AgentRuleDescription initializeRuleDescription() {
			return new AgentRuleDescription(AgentCFPRule.this.ruleType, CFP_HANDLE_NO_RESPONSES_STEP,
					format("%s - no responses received", AgentCFPRule.this.name),
					"rule executed when there are 0 responses to CFP");
		}

		@Override
		public AgentRule copy() {
			return new HandleNoResponsesRule();
		}
	}

	// RULE EXECUTED WHEN THERE ARE NO PROPOSALS
	class HandleNoProposalsRule extends AgentBasicRule<T, E> {

		public HandleNoProposalsRule() {
			super(AgentCFPRule.this.controller);
			this.isRuleStep = true;
		}

		@Override
		public void executeRule(final RuleSetFacts facts) {
			if (nonNull(AgentCFPRule.this.initialParameters)) {
				AgentCFPRule.this.initialParameters.replace(FACTS, facts);
			}

			if (isNull(expressionHandleNoProposals)) {
				handleNoProposals(facts);
			} else {
				MVEL.executeExpression(expressionHandleNoProposals, AgentCFPRule.this.initialParameters);
			}
		}

		@Override
		public AgentRuleDescription initializeRuleDescription() {
			return new AgentRuleDescription(AgentCFPRule.this.ruleType, CFP_HANDLE_NO_AVAILABLE_AGENTS_STEP,
					format("%s - no proposals received", AgentCFPRule.this.name),
					"rule executed when there are 0 proposals to CFP");
		}

		@Override
		public AgentRule copy() {
			return new HandleNoProposalsRule();
		}
	}

	// RULE EXECUTED WHEN THERE ARE PROPOSALS
	class HandleProposalsRule extends AgentBasicRule<T, E> {

		public HandleProposalsRule() {
			super(AgentCFPRule.this.controller);
			this.isRuleStep = true;
		}

		@Override
		public void executeRule(final RuleSetFacts facts) {
			final ACLMessage bestProposal = facts.get(CFP_BEST_MESSAGE);
			final Collection<ACLMessage> allProposals = facts.get(CFP_RECEIVED_PROPOSALS);
			if (nonNull(AgentCFPRule.this.initialParameters)) {
				AgentCFPRule.this.initialParameters.replace(FACTS, facts);
			}

			if (isNull(expressionHandleProposals)) {
				handleProposals(bestProposal, allProposals, facts);
			} else {
				AgentCFPRule.this.initialParameters.put(BEST_PROPOSAL, bestProposal);
				AgentCFPRule.this.initialParameters.put(ALL_PROPOSALS, allProposals);
				MVEL.executeExpression(expressionHandleProposals, AgentCFPRule.this.initialParameters);
				AgentCFPRule.this.initialParameters.remove(BEST_PROPOSAL);
				AgentCFPRule.this.initialParameters.remove(ALL_PROPOSALS);
			}
		}

		@Override
		public AgentRuleDescription initializeRuleDescription() {
			return new AgentRuleDescription(AgentCFPRule.this.ruleType, CFP_HANDLE_SELECTED_PROPOSAL_STEP,
					format("%s - handle proposals", AgentCFPRule.this.name),
					"rule executed when there are some proposals to CFP");
		}

		@Override
		public AgentRule copy() {
			return new HandleProposalsRule();
		}
	}

}
