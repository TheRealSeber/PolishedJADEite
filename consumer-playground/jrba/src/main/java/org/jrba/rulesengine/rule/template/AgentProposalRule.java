package org.jrba.rulesengine.rule.template;

import static jade.lang.acl.ACLMessage.PROPOSE;
import static java.lang.String.format;
import static java.util.Objects.isNull;
import static java.util.Objects.nonNull;
import static org.jrba.rulesengine.constants.FactTypeConstants.PROPOSAL_ACCEPT_MESSAGE;
import static org.jrba.rulesengine.constants.FactTypeConstants.PROPOSAL_CREATE_MESSAGE;
import static org.jrba.rulesengine.constants.FactTypeConstants.PROPOSAL_REJECT_MESSAGE;
import static org.jrba.rulesengine.constants.FactTypeConstants.RULE_SET_IDX;
import static org.jrba.rulesengine.constants.MVELParameterConstants.ACCEPT_MESSAGE;
import static org.jrba.rulesengine.constants.MVELParameterConstants.FACTS;
import static org.jrba.rulesengine.constants.MVELParameterConstants.REJECT_MESSAGE;
import static org.jrba.rulesengine.constants.RuleTypeConstants.DEFAULT_PROPOSAL_RULE;
import static org.jrba.rulesengine.types.rulesteptype.RuleStepTypeEnum.PROPOSAL_CREATE_STEP;
import static org.jrba.rulesengine.types.rulesteptype.RuleStepTypeEnum.PROPOSAL_HANDLE_ACCEPT_STEP;
import static org.jrba.rulesengine.types.rulesteptype.RuleStepTypeEnum.PROPOSAL_HANDLE_REJECT_STEP;
import static org.jrba.rulesengine.types.ruletype.AgentRuleTypeEnum.PROPOSAL;

import java.io.Serializable;
import java.util.ArrayList;
import java.util.List;

import org.jrba.agentmodel.domain.node.AgentNode;
import org.jrba.agentmodel.domain.props.AgentProps;
import org.jrba.rulesengine.RulesController;
import org.jrba.rulesengine.rest.domain.ProposalRuleRest;
import org.jrba.rulesengine.rule.AgentBasicRule;
import org.jrba.rulesengine.rule.AgentRule;
import org.jrba.rulesengine.rule.AgentRuleDescription;
import org.jrba.rulesengine.ruleset.RuleSetFacts;
import org.jrba.utils.messages.MessageBuilder;
import org.mvel2.MVEL;

import jade.lang.acl.ACLMessage;
import lombok.Getter;

/**
 * Abstract class defining structure of a rule which handles default Proposal initiator behaviour.
 *
 * @param <E> type of node connected to the Agent
 * @param <T> type of properties of Agent
 */
@Getter
public class AgentProposalRule<T extends AgentProps, E extends AgentNode<T>> extends AgentBasicRule<T, E> {

	protected Serializable expressionCreateProposal;
	protected Serializable expressionHandleAcceptProposal;
	protected Serializable expressionHandleRejectProposal;

	/**
	 * Copy constructor.
	 *
	 * @param rule rule that is to be copied
	 */
	public AgentProposalRule(final AgentProposalRule<T, E> rule) {
		super(rule);
		this.expressionCreateProposal = rule.getExpressionCreateProposal();
		this.expressionHandleAcceptProposal = rule.getExpressionHandleAcceptProposal();
		this.expressionHandleRejectProposal = rule.getExpressionHandleRejectProposal();
	}

	/**
	 * Constructor
	 *
	 * @param controller rules controller connected to the agent
	 */
	protected AgentProposalRule(final RulesController<T, E> controller) {
		super(controller);
		initializeSteps();
	}

	/**
	 * Constructor
	 *
	 * @param ruleRest rest representation of agent rule
	 */
	public AgentProposalRule(final ProposalRuleRest ruleRest) {
		super(ruleRest);
		if (nonNull(ruleRest.getCreateProposalMessage())) {
			this.expressionCreateProposal = MVEL.compileExpression(
					imports + " " + ruleRest.getCreateProposalMessage());
		}
		if (nonNull(ruleRest.getHandleAcceptProposal())) {
			this.expressionHandleAcceptProposal = MVEL.compileExpression(
					imports + " " + ruleRest.getHandleAcceptProposal());
		}
		if (nonNull(ruleRest.getHandleRejectProposal())) {
			this.expressionHandleRejectProposal = MVEL.compileExpression(
					imports + " " + ruleRest.getHandleRejectProposal());
		}
		initializeSteps();
	}

	/**
	 * Method assigns a list of PROPOSE protocol steps.
	 */
	public void initializeSteps() {
		stepRules = new ArrayList<>(List.of(
				new CreateProposalMessageRule(),
				new HandleAcceptProposalRule(),
				new HandleRejectProposalRule())
		);
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
		return PROPOSAL.getType();
	}

	/**
	 * Method executed when proposal message is to be created.
	 *
	 * @param facts facts with additional parameters
	 * @return initialized proposal message
	 */
	protected ACLMessage createProposalMessage(final RuleSetFacts facts) {
		return MessageBuilder.builder(facts.get(RULE_SET_IDX).toString(), PROPOSE).build();
	}

	/**
	 * Method executed when ACCEPT_PROPOSAL message is to be handled.
	 *
	 * @param facts  facts facts with additional parameters
	 * @param accept message accepting the proposal
	 */
	protected void handleAcceptProposal(final ACLMessage accept, final RuleSetFacts facts) {
		// TO BE OVERRIDDEN BY USER
	}

	/**
	 * Method executed when REJECT_PROPOSAL message is to be handled.
	 *
	 * @param facts  facts facts with additional parameters
	 * @param reject message rejecting the proposal
	 */
	protected void handleRejectProposal(final ACLMessage reject, final RuleSetFacts facts) {
		// TO BE OVERRIDDEN BY USER
	}

	@Override
	public AgentRuleDescription initializeRuleDescription() {
		return new AgentRuleDescription(DEFAULT_PROPOSAL_RULE,
				"default proposal rule",
				"default implementation of a rule that handles each step of FIPA PROPOSE protocol");
	}

	@Override
	public AgentRule copy() {
		return new AgentProposalRule<>(this);
	}

	// RULE EXECUTED WHEN PROPOSAL MESSAGE IS TO BE CREATED
	class CreateProposalMessageRule extends AgentBasicRule<T, E> {

		public CreateProposalMessageRule() {
			super(AgentProposalRule.this.controller);
			this.isRuleStep = true;
		}

		@Override
		public void executeRule(final RuleSetFacts facts) {
			if (nonNull(AgentProposalRule.this.initialParameters)) {
				AgentProposalRule.this.initialParameters.replace(FACTS, facts);
			}
			final ACLMessage proposal = isNull(expressionCreateProposal) ?
					createProposalMessage(facts) :
					(ACLMessage) MVEL.executeExpression(expressionCreateProposal,
							AgentProposalRule.this.initialParameters);
			facts.put(PROPOSAL_CREATE_MESSAGE, proposal);
		}

		@Override
		public AgentRuleDescription initializeRuleDescription() {
			return new AgentRuleDescription(AgentProposalRule.this.ruleType, PROPOSAL_CREATE_STEP,
					format("%s - create proposal message", AgentProposalRule.this.name),
					"rule performed when proposal message sent to other agents is to be created");
		}

		@Override
		public AgentRule copy() {
			return new CreateProposalMessageRule();
		}
	}

	// RULE EXECUTED WHEN ACCEPT_PROPOSAL MESSAGE IS RECEIVED
	class HandleAcceptProposalRule extends AgentBasicRule<T, E> {

		public HandleAcceptProposalRule() {
			super(AgentProposalRule.this.controller);
			this.isRuleStep = true;
		}

		@Override
		public void executeRule(final RuleSetFacts facts) {
			final ACLMessage acceptMessage = facts.get(PROPOSAL_ACCEPT_MESSAGE);
			if (nonNull(AgentProposalRule.this.initialParameters)) {
				AgentProposalRule.this.initialParameters.replace(FACTS, facts);
			}

			if (isNull(expressionHandleAcceptProposal)) {
				handleAcceptProposal(acceptMessage, facts);
			} else {
				AgentProposalRule.this.initialParameters.put(ACCEPT_MESSAGE, acceptMessage);
				MVEL.executeExpression(expressionHandleAcceptProposal, AgentProposalRule.this.initialParameters);
				AgentProposalRule.this.initialParameters.remove(ACCEPT_MESSAGE);
			}
		}

		@Override
		public AgentRuleDescription initializeRuleDescription() {
			return new AgentRuleDescription(AgentProposalRule.this.ruleType, PROPOSAL_HANDLE_ACCEPT_STEP,
					format("%s - handle accept proposal", AgentProposalRule.this.name),
					"rule that handles cases when ACCEPT_PROPOSAL message is received");
		}

		@Override
		public AgentRule copy() {
			return new HandleAcceptProposalRule();
		}
	}

	// RULE EXECUTED WHEN ACCEPT_PROPOSAL MESSAGE IS RECEIVED
	class HandleRejectProposalRule extends AgentBasicRule<T, E> {

		public HandleRejectProposalRule() {
			super(AgentProposalRule.this.controller);
			this.isRuleStep = true;
		}

		@Override
		public void executeRule(final RuleSetFacts facts) {
			final ACLMessage rejectMessage = facts.get(PROPOSAL_REJECT_MESSAGE);
			if (nonNull(AgentProposalRule.this.initialParameters)) {
				AgentProposalRule.this.initialParameters.replace(FACTS, facts);
			}

			if (isNull(expressionHandleRejectProposal)) {
				handleRejectProposal(rejectMessage, facts);
			} else {
				AgentProposalRule.this.initialParameters.put(REJECT_MESSAGE, rejectMessage);
				MVEL.executeExpression(expressionHandleRejectProposal, AgentProposalRule.this.initialParameters);
				AgentProposalRule.this.initialParameters.remove(REJECT_MESSAGE);
			}
		}

		@Override
		public AgentRuleDescription initializeRuleDescription() {
			return new AgentRuleDescription(AgentProposalRule.this.ruleType, PROPOSAL_HANDLE_REJECT_STEP,
					format("%s - handle reject proposal", AgentProposalRule.this.name),
					"rule that handles cases when REJECT_PROPOSAL message is received");
		}

		@Override
		public AgentRule copy() {
			return new HandleRejectProposalRule();
		}
	}

}
