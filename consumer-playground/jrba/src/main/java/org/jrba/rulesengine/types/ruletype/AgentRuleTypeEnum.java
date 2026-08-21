package org.jrba.rulesengine.types.ruletype;

import lombok.AllArgsConstructor;
import lombok.Getter;

/**
 * Enum defines basic agent rule types
 */
@Getter
@AllArgsConstructor
public enum AgentRuleTypeEnum implements AgentRuleType {

	BASIC("BASIC"),
	COMBINED("COMBINED"),
	BEHAVIOUR("BEHAVIOUR"),
	CHAIN("CHAIN"),
	CFP("CFP"),
	LISTENER("LISTENER"),
	LISTENER_SINGLE("LISTENER_SINGLE"),
	PERIODIC("PERIODIC"),
	PROPOSAL("PROPOSAL"),
	REQUEST("REQUEST"),
	SCHEDULED("SCHEDULED"),
	SEARCH("SEARCH"),
	SUBSCRIPTION("SUBSCRIPTION");

	final String type;
}
