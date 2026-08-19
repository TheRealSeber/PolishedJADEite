package org.jrba.rulesengine.rest.domain;

import java.io.Serializable;
import java.util.List;

import org.jrba.rulesengine.types.rulecombinationtype.AgentCombinedRuleType;

import com.fasterxml.jackson.annotation.JsonInclude;

import lombok.Getter;
import lombok.Setter;

/**
 * REST representation of AgentCombinedRule.
 */
@Getter
@Setter
@JsonInclude(JsonInclude.Include.NON_NULL)
public class CombinedRuleRest extends RuleRest implements Serializable {

	AgentCombinedRuleType combinedRuleType;
	List<RuleRest> rulesToCombine;

}
