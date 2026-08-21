package org.jrba.rulesengine.rest.domain;

import java.io.Serializable;

import com.fasterxml.jackson.annotation.JsonInclude;

import lombok.Getter;
import lombok.Setter;

/**
 * REST representation of AgentSingleMessageListenerRule.
 */
@Getter
@Setter
@JsonInclude(JsonInclude.Include.NON_NULL)
public class SingleMessageListenerRuleRest extends RuleRest implements Serializable {

	String constructMessageTemplate;
	String specifyExpirationTime;
	String handleMessageProcessing;
	String handleMessageNotReceived;

}
