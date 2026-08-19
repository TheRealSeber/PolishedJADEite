package org.jrba.agentmodel.domain.args;

import org.immutables.value.Value;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.databind.annotation.JsonDeserialize;
import com.fasterxml.jackson.databind.annotation.JsonSerialize;

/**
 * Interface defining common arguments of system agents.
 * It can be used to construct agent controllers.
 */
@JsonSerialize(as = ImmutableAgentArgs.class)
@JsonDeserialize(as = ImmutableAgentArgs.class)
@JsonIgnoreProperties(value = { "objectArray" })
@Value.Immutable
public interface AgentArgs {

	/**
	 * @return agent name
	 */
	String getName();

	/**
	 * @return agent arguments as object array
	 */
	default Object[] getObjectArray() {
		return new Object[] { getName() };
	}
}
