package org.jrba.environment.types;

import lombok.AllArgsConstructor;
import lombok.Getter;

/**
 * Enum with default event types
 */
@Getter
@AllArgsConstructor
public enum EventTypeEnum implements EventType {

	BASIC_EVENT(null),
	MODIFY_RULE_SET("AGENT_MODIFY_RULE_SET_RULE");

	final String ruleType;
}
