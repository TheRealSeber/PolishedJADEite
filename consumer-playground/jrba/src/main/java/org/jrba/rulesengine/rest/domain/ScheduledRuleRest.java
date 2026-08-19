package org.jrba.rulesengine.rest.domain;

import java.io.Serializable;

import com.fasterxml.jackson.annotation.JsonInclude;

import lombok.Getter;
import lombok.Setter;

/**
 * REST representation of AgentScheduledRule.
 */
@Getter
@Setter
@JsonInclude(JsonInclude.Include.NON_NULL)
public class ScheduledRuleRest extends RuleRest implements Serializable {

	String specifyTime;
	String handleActionTrigger;
	String evaluateBeforeTrigger;

}
