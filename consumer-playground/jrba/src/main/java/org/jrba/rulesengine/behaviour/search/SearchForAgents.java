package org.jrba.rulesengine.behaviour.search;

import static org.jrba.utils.mapper.FactsMapper.mapToRuleSetFacts;
import static org.jrba.rulesengine.constants.FactTypeConstants.RESULT;
import static org.jrba.rulesengine.constants.FactTypeConstants.RULE_STEP;
import static org.jrba.rulesengine.constants.FactTypeConstants.RULE_TYPE;
import static org.jrba.rulesengine.types.rulesteptype.RuleStepTypeEnum.SEARCH_AGENTS_STEP;
import static org.jrba.rulesengine.types.rulesteptype.RuleStepTypeEnum.SEARCH_HANDLE_NO_RESULTS_STEP;
import static org.jrba.rulesengine.types.rulesteptype.RuleStepTypeEnum.SEARCH_HANDLE_RESULTS_STEP;

import java.util.Set;

import org.jrba.rulesengine.RulesController;
import org.jrba.rulesengine.ruleset.RuleSetFacts;

import jade.core.AID;
import jade.core.Agent;
import jade.core.behaviours.OneShotBehaviour;

/**
 * Abstract behaviour providing template for handling agents search in DF
 */
public class SearchForAgents extends OneShotBehaviour {

	private final RuleSetFacts facts;
	protected RulesController<?, ?> controller;

	private SearchForAgents(final Agent agent, final RuleSetFacts facts, final String ruleType,
			final RulesController<?, ?> controller) {
		super(agent);
		this.facts = mapToRuleSetFacts(facts);
		this.facts.put(RULE_TYPE, ruleType);
		this.controller = controller;
	}

	/**
	 * Behaviour creator
	 *
	 * @param agent      agent executing the behaviour
	 * @param facts      facts under which the search is to be performed
	 * @param ruleType   type of the rule that handles search execution
	 * @param controller rules controller
	 */
	public static SearchForAgents create(final Agent agent, final RuleSetFacts facts, final String ruleType,
			final RulesController<?, ?> controller) {
		return new SearchForAgents(agent, facts, ruleType, controller);
	}

	/**
	 * Method looks for agent which registered given service.
	 */
	@Override
	public void action() {
		facts.put(RULE_STEP, SEARCH_AGENTS_STEP.getType());
		controller.fire(facts);

		final Set<AID> foundAgents = facts.get(RESULT);

		if (foundAgents.isEmpty()) {
			facts.put(RULE_STEP, SEARCH_HANDLE_NO_RESULTS_STEP.getType());
		} else {
			facts.put(RULE_STEP, SEARCH_HANDLE_RESULTS_STEP.getType());
		}
		controller.fire(facts);
		postProcessSearch(facts);
	}

	/**
	 * Method can be optionally overridden in order to perform facts-based actions at the end of search execution
	 */
	protected void postProcessSearch(final RuleSetFacts facts) {
		// to be overridden if necessary
	}
}
