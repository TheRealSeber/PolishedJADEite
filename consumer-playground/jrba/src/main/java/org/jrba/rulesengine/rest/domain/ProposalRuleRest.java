package org.jrba.rulesengine.rest.domain;

import java.io.Serializable;

import com.fasterxml.jackson.annotation.JsonInclude;

import lombok.Getter;
import lombok.Setter;

/**
 * REST representation of AgentProposalRule.
 */
@Getter
@Setter
@JsonInclude(JsonInclude.Include.NON_NULL)
public class ProposalRuleRest extends RuleRest implements Serializable {

	String createProposalMessage;
	String handleAcceptProposal;
	String handleRejectProposal;
}
