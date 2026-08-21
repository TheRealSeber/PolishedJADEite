package org.jrba.rulesengine.rest.controller;

import static java.util.Optional.ofNullable;
import static org.jrba.rulesengine.rest.RuleSetRestApi.getAgentNodes;
import static org.jrba.rulesengine.rest.RuleSetRestApi.getAvailableRuleSets;

import org.jrba.agentmodel.domain.node.AgentNode;
import org.jrba.exception.CannotFindAgentException;
import org.jrba.exception.CannotFindRuleSetException;
import org.jrba.rulesengine.rest.domain.RuleSetRest;
import org.jrba.rulesengine.ruleset.RuleSet;
import org.jrba.rulesengine.ruleset.domain.ModifyAgentRuleSetEvent;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class RuleSetController {

	@PostMapping(value = "/ruleSet", consumes = "application/json")
	public ResponseEntity<String> injectNewRuleSet(@RequestBody final RuleSetRest ruleSet) {
		final RuleSet newRuleSet = new RuleSet(ruleSet);

		getAvailableRuleSets().put(newRuleSet.getName(), newRuleSet);
		return ResponseEntity.ok("Rule set successfully injected");
	}

	@PutMapping(value = "/ruleSet/modify", consumes = "application/json")
	public ResponseEntity<String> modifyRuleSet(@RequestBody final RuleSetRest ruleSet,
			@RequestParam String agentName, @RequestParam boolean replaceFully) {
		final RuleSet newRuleSet = new RuleSet(ruleSet);

		triggerRuleSetChangeEvent(newRuleSet, agentName, replaceFully);
		return ResponseEntity.ok("Rule set change event injected in agent node.");
	}

	@PutMapping(value = "/ruleSet/change", consumes = "application/json")
	public ResponseEntity<String> changeRuleSet(@RequestParam final String ruleSetName,
			@RequestParam String agentName, @RequestParam boolean replaceFully) {
		final RuleSet newRuleSet = ofNullable(getAvailableRuleSets().get(ruleSetName))
				.orElseThrow(CannotFindRuleSetException::new);

		triggerRuleSetChangeEvent(newRuleSet, agentName, replaceFully);
		return ResponseEntity.ok("Rule set change event injected in agent node.");
	}

	private void triggerRuleSetChangeEvent(final RuleSet ruleSet, final String agentName, final boolean replaceFully) {
		final AgentNode agentNode = getAgentNodes().stream()
				.filter(node -> node.getAgentName().equals(agentName)).findFirst()
				.orElseThrow(CannotFindAgentException::new);
		agentNode.addEvent(new ModifyAgentRuleSetEvent(replaceFully, ruleSet, agentName));
	}
}
