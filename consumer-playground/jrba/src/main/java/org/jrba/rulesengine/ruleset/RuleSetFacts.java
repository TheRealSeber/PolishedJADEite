package org.jrba.rulesengine.ruleset;

import org.jeasy.rules.api.Facts;

/**
 * Abstract class extending traditional RuleSetFacts with assigned rule set index.
 */
public class RuleSetFacts extends Facts {

	/**
	 * Constructor
	 *
	 * @param ruleSetIndex new rule set index
	 */
	public RuleSetFacts(final int ruleSetIndex) {
		super();
		put("rule-set-idx", ruleSetIndex);
	}
}
