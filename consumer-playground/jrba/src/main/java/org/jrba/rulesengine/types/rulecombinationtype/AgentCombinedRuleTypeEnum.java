package org.jrba.rulesengine.types.rulecombinationtype;

import lombok.AllArgsConstructor;
import lombok.Getter;

/**
 * Enum defines basic combined rule types
 */
@Getter
@AllArgsConstructor
public enum AgentCombinedRuleTypeEnum implements AgentCombinedRuleType {

	EXECUTE_FIRST("EXECUTE_FIRST"),
	EXECUTE_ALL("EXECUTE_ALL");

	final String type;
}
