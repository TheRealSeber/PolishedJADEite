package org.jrba.rulesengine.rule;

import static java.util.Collections.singletonList;
import static org.jrba.rulesengine.constants.RuleTypeConstants.BASIC_RULE;

import java.util.List;

import org.jeasy.rules.api.Rule;
import org.jrba.rulesengine.RulesController;
import org.jrba.rulesengine.ruleset.RuleSetFacts;

/**
 * Interface representing common agent rule.
 * It is implemented by all types of agent rules.
 */
public interface AgentRule extends Rule {

	/**
	 * @return name of the agent type
	 */
	String getAgentType();

	/**
	 * @return overall name of the rule type
	 */
	String getAgentRuleType();

	/**
	 * @return name of the rule type
	 */
	String getRuleType();

	/**
	 * @return name of the sub-rule type
	 */
	String getSubRuleType();

	/**
	 * @return name of the rule step
	 */
	String getStepType();

	/**
	 * @return boolean indicating if the rule is a step
	 */
	boolean isRuleStep();

	/**
	 * @return constructed rule Object
	 */
	default List<AgentRule> getRules() {
		return singletonList(this);
	}

	/**
	 * Method performs default evaluation of rule conditions
	 *
	 * @param facts facts used in evaluation
	 * @return boolean indicating if conditions are met
	 */
	default boolean evaluateRule(RuleSetFacts facts) {
		return true;
	}

	/**
	 * Method executes given rule
	 *
	 * @param facts facts used in evaluation
	 */
	default void executeRule(RuleSetFacts facts) {
	}

	/**
	 * Method initialize default rule metadata
	 *
	 * @return rule description
	 */
	default AgentRuleDescription initializeRuleDescription() {
		return new AgentRuleDescription(BASIC_RULE, "basic agent rule", "default rule definition");
	}

	/**
	 * Method connects agent rule with controller
	 *
	 * @param rulesController rules controller connected to the agent
	 */
	default void connectToController(final RulesController<?, ?> rulesController) {
	}

	/**
	 * Method clones a given rule to a new object instance
	 *
	 * @return cloned rule
	 */
	default AgentRule copy() {
		return null;
	}
}
