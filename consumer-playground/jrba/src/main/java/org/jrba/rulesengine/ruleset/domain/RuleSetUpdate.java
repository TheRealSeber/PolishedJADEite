package org.jrba.rulesengine.ruleset.domain;

import org.immutables.value.Value;

import com.fasterxml.jackson.databind.annotation.JsonDeserialize;
import com.fasterxml.jackson.databind.annotation.JsonSerialize;

/**
 * Object stores the data used in updating system rule set
 */
@JsonSerialize(as = ImmutableRuleSetUpdate.class)
@JsonDeserialize(as = ImmutableRuleSetUpdate.class)
@Value.Immutable
public interface RuleSetUpdate {

	int getRuleSetIdx();

	String getRuleSetType();
}
