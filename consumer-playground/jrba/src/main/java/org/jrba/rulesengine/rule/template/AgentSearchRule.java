package org.jrba.rulesengine.rule.template;

import static java.lang.String.format;
import static java.util.Objects.isNull;
import static java.util.Objects.nonNull;
import static org.jrba.rulesengine.constants.FactTypeConstants.RESULT;
import static org.jrba.rulesengine.constants.MVELParameterConstants.AGENTS;
import static org.jrba.rulesengine.constants.MVELParameterConstants.FACTS;
import static org.jrba.rulesengine.constants.RuleTypeConstants.DEFAULT_SEARCH_RULE;
import static org.jrba.rulesengine.types.rulesteptype.RuleStepTypeEnum.SEARCH_AGENTS_STEP;
import static org.jrba.rulesengine.types.rulesteptype.RuleStepTypeEnum.SEARCH_HANDLE_NO_RESULTS_STEP;
import static org.jrba.rulesengine.types.rulesteptype.RuleStepTypeEnum.SEARCH_HANDLE_RESULTS_STEP;
import static org.jrba.rulesengine.types.ruletype.AgentRuleTypeEnum.SEARCH;

import java.io.Serializable;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

import org.jrba.agentmodel.domain.node.AgentNode;
import org.jrba.agentmodel.domain.props.AgentProps;
import org.jrba.rulesengine.RulesController;
import org.jrba.rulesengine.rest.domain.SearchRuleRest;
import org.jrba.rulesengine.rule.AgentBasicRule;
import org.jrba.rulesengine.rule.AgentRule;
import org.jrba.rulesengine.rule.AgentRuleDescription;
import org.jrba.rulesengine.ruleset.RuleSetFacts;
import org.mvel2.MVEL;

import jade.core.AID;
import lombok.Getter;

/**
 * Abstract class defining structure of a rule which handles default DF search behaviour.
 *
 * @param <E> type of node connected to the Agent
 * @param <T> type of properties of Agent
 */
@Getter
public class AgentSearchRule<T extends AgentProps, E extends AgentNode<T>> extends AgentBasicRule<T, E> {

	protected Serializable expressionSearchAgents;
	protected Serializable expressionHandleNoResults;
	protected Serializable expressionHandleResults;

	/**
	 * Copy constructor.
	 *
	 * @param rule rule that is to be copied
	 */
	public AgentSearchRule(final AgentSearchRule<T, E> rule) {
		super(rule);
		this.expressionSearchAgents = rule.getExpressionSearchAgents();
		this.expressionHandleNoResults = rule.getExpressionHandleNoResults();
		this.expressionHandleResults = rule.getExpressionHandleResults();
	}

	/**
	 * Constructor
	 *
	 * @param controller rules controller connected to the agent
	 */
	protected AgentSearchRule(final RulesController<T, E> controller) {
		super(controller);
		initializeSteps();
	}

	/**
	 * Constructor
	 *
	 * @param ruleRest rest representation of agent rule
	 */
	public AgentSearchRule(final SearchRuleRest ruleRest) {
		super(ruleRest);
		if (nonNull(ruleRest.getSearchAgents())) {
			this.expressionSearchAgents = MVEL.compileExpression(
					imports + " " + ruleRest.getSearchAgents());
		}
		if (nonNull(ruleRest.getHandleNoResults())) {
			this.expressionHandleNoResults = MVEL.compileExpression(imports + " " + ruleRest.getHandleNoResults());
		}
		if (nonNull(ruleRest.getHandleResults())) {
			this.expressionHandleResults = MVEL.compileExpression(
					imports + " " + ruleRest.getHandleResults());
		}
		initializeSteps();
	}

	/**
	 * Method assigns a list of search rule steps.
	 */
	public void initializeSteps() {
		stepRules = new ArrayList<>(List.of(new SearchForAgentsRule(), new NoResultsRule(), new AgentsFoundRule()));
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
		return SEARCH.getType();
	}

	/**
	 * Method searches for the agents in DF.
	 *
	 * @param facts facts with additional parameters
	 * @return Set of AIDs of agents found by DF
	 */
	protected Set<AID> searchAgents(final RuleSetFacts facts) {
		return new HashSet<>();
	}

	/**
	 * Method executed when DF retrieved no results.
	 *
	 * @param facts facts with additional parameters
	 */
	protected void handleNoResults(final RuleSetFacts facts) {
		// TO BE OVERRIDDEN BY USER
	}

	/**
	 * Method executed when DF retrieved results.
	 *
	 * @param facts facts with additional parameters
	 * @param dfResults Set of AIDs of found agents
	 */
	protected void handleResults(final Set<AID> dfResults, final RuleSetFacts facts) {
		// TO BE OVERRIDDEN BY USER
	}

	@Override
	public AgentRuleDescription initializeRuleDescription() {
		return new AgentRuleDescription(DEFAULT_SEARCH_RULE,
				"default search rule",
				"default implementation of a rule that searches for pre-defined agent services");
	}

	@Override
	public AgentRule copy() {
		return new AgentSearchRule<>(this);
	}

	// RULE EXECUTED WHEN DF IS TO BE SEARCHED
	class SearchForAgentsRule extends AgentBasicRule<T, E> {

		public SearchForAgentsRule() {
			super(AgentSearchRule.this.controller);
			this.isRuleStep = true;
		}

		@Override
		public void executeRule(final RuleSetFacts facts) {
			if (nonNull(AgentSearchRule.this.initialParameters)) {
				AgentSearchRule.this.initialParameters.replace(FACTS, facts);
			}

			final Set<AID> result = isNull(expressionSearchAgents) ?
					searchAgents(facts) :
					(Set<AID>) MVEL.executeExpression(expressionSearchAgents, AgentSearchRule.this.initialParameters);
			facts.put(RESULT, result);
		}

		@Override
		public AgentRuleDescription initializeRuleDescription() {
			return new AgentRuleDescription(AgentSearchRule.this.ruleType, SEARCH_AGENTS_STEP,
					format("%s - search for agents", AgentSearchRule.this.name),
					"rule performed when searching for agents in DF");
		}

		@Override
		public AgentRule copy() {
			return new SearchForAgentsRule();
		}
	}

	// RULE EXECUTED WHEN DF RETURNED EMPTY RESULT LIST
	class NoResultsRule extends AgentBasicRule<T, E> {

		public NoResultsRule() {
			super(AgentSearchRule.this.controller);
			this.isRuleStep = true;
		}

		@Override
		public void executeRule(final RuleSetFacts facts) {
			if (nonNull(AgentSearchRule.this.initialParameters)) {
				AgentSearchRule.this.initialParameters.replace(FACTS, facts);
			}

			if (isNull(expressionHandleNoResults)) {
				handleNoResults(facts);
			} else {
				MVEL.executeExpression(expressionHandleNoResults, AgentSearchRule.this.initialParameters);
			}
		}

		@Override
		public AgentRuleDescription initializeRuleDescription() {
			return new AgentRuleDescription(AgentSearchRule.this.ruleType, SEARCH_HANDLE_NO_RESULTS_STEP,
					format("%s - no results", AgentSearchRule.this.name),
					"rule that handles case when no DF results were retrieved");
		}

		@Override
		public AgentRule copy() {
			return new NoResultsRule();
		}
	}

	// RULE EXECUTED WHEN DF RETURNED SET OF AGENTS
	class AgentsFoundRule extends AgentBasicRule<T, E> {

		public AgentsFoundRule() {
			super(AgentSearchRule.this.controller);
			this.isRuleStep = true;
		}

		@Override
		public void executeRule(final RuleSetFacts facts) {
			if (nonNull(AgentSearchRule.this.initialParameters)) {
				AgentSearchRule.this.initialParameters.replace(FACTS, facts);
			}

			final Set<AID> agents = facts.get(RESULT);

			if (isNull(expressionHandleResults)) {
				handleResults(agents, facts);
			} else {
				AgentSearchRule.this.initialParameters.put(AGENTS, agents);
				MVEL.executeExpression(expressionHandleResults, AgentSearchRule.this.initialParameters);
				AgentSearchRule.this.initialParameters.remove(AGENTS);
			}
		}

		@Override
		public AgentRuleDescription initializeRuleDescription() {
			return new AgentRuleDescription(AgentSearchRule.this.ruleType, SEARCH_HANDLE_RESULTS_STEP,
					format("%s - agents found", AgentSearchRule.this.name),
					"rule triggerred when DF returned set of agents");
		}

		@Override
		public AgentRule copy() {
			return new AgentsFoundRule();
		}
	}

}
