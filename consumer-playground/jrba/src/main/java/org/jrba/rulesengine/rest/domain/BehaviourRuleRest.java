package org.jrba.rulesengine.rest.domain;

import java.io.Serializable;
import java.util.List;

import com.fasterxml.jackson.annotation.JsonInclude;

import lombok.Getter;
import lombok.Setter;

/**
 * REST representation of AgentBehaviourRule.
 */
@Getter
@Setter
@JsonInclude(JsonInclude.Include.NON_NULL)
public class BehaviourRuleRest extends RuleRest implements Serializable {

	List<String> behaviours;
}
