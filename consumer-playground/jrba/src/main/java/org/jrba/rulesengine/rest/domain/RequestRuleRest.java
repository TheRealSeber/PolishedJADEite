package org.jrba.rulesengine.rest.domain;

import java.io.Serializable;

import com.fasterxml.jackson.annotation.JsonInclude;

import lombok.Getter;
import lombok.Setter;

/**
 * REST representation of AgentRequestRule.
 */
@Getter
@Setter
@JsonInclude(JsonInclude.Include.NON_NULL)
public class RequestRuleRest extends RuleRest implements Serializable {

	String createRequestMessage;
	String evaluateBeforeForAll;
	String handleInform;
	String handleFailure;
	String handleRefuse;
	String handleAllResults;
}
