package org.jrba.rulesengine.rule;

import org.jrba.rulesengine.types.rulesteptype.RuleStepType;

/**
 * Class storing common properties which describe a given rule
 *
 * @param ruleType        type of the rule
 * @param subType         secondary type used in combined rules
 * @param stepType        optional type of rule step
 * @param ruleName        name of the rule
 * @param ruleDescription description of the rule
 */
public record AgentRuleDescription(String ruleType, String subType, String stepType, String ruleName,
								   String ruleDescription) {

	/**
	 * Agent description constructor.
	 *
	 * @param ruleType name of the rule type
	 * @param ruleName name of the rule
	 * @param ruleDescription rule description
	 */
	public AgentRuleDescription(final String ruleType, final String ruleName, final String ruleDescription) {
		this(ruleType, null, null, ruleName, ruleDescription);
	}

	/**
	 * Agent description constructor.
	 *
	 * @param ruleType name of the rule type
	 * @param subType name of the sub-rule type
	 * @param ruleName name of the rule
	 * @param ruleDescription rule description
	 */
	public AgentRuleDescription(final String ruleType, final String subType, final String ruleName,
			final String ruleDescription) {
		this(ruleType, subType, null, ruleName, ruleDescription);
	}

	/**
	 * Agent description constructor.
	 *
	 * @param ruleType name of the rule type
	 * @param stepType name of the rule step type
	 * @param ruleName name of the rule
	 * @param ruleDescription rule description
	 */
	public AgentRuleDescription(final String ruleType, final RuleStepType stepType, final String ruleName,
			final String ruleDescription) {
		this(ruleType, null, stepType.getType(), ruleName, ruleDescription);
	}
}
