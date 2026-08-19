package org.jrba.agentmodel.types;

import lombok.AllArgsConstructor;
import lombok.Getter;

/**
 * Enum with default agent types
 */
@Getter
@AllArgsConstructor
public enum AgentTypeEnum implements AgentType {

	BASIC("BASIC");

	final String name;
}
