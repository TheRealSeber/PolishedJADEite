package org.jrba.utils.rules;

import static org.jrba.rulesengine.constants.FactTypeConstants.RULE_SET_IDX;

import java.util.function.ToIntFunction;

import org.jrba.rulesengine.RulesController;
import org.jeasy.rules.api.Facts;

/**
 * Enum storing types of methods that can be applied to select the rule set
 */
public enum RuleSetSelector {

	SELECT_BY_FACTS_IDX, SELECT_LATEST;

	/**
	 * Method returns selector that can be used to choose rule set index.
	 *
	 * @param selector type of selector
	 * @return selector function
	 */
	public static ToIntFunction<Facts> selectRuleSetIndex(final RuleSetSelector selector,
			final RulesController<?, ?> controller) {
		return switch (selector) {
			case SELECT_BY_FACTS_IDX -> facts -> facts.get(RULE_SET_IDX);
			case SELECT_LATEST -> facts -> controller.getLatestLongTermRuleSetIdx().get();
		};
	}
}
