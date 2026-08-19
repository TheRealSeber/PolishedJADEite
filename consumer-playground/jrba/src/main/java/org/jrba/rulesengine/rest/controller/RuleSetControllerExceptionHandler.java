package org.jrba.rulesengine.rest.controller;

import static org.springframework.http.HttpStatus.NOT_FOUND;

import org.jrba.exception.CannotFindAgentException;
import org.jrba.exception.CannotFindRuleSetException;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ControllerAdvice;
import org.springframework.web.bind.annotation.ExceptionHandler;

@ControllerAdvice
public class RuleSetControllerExceptionHandler {

	@ExceptionHandler({ CannotFindAgentException.class })
	public ResponseEntity<Object> handleNoAgentFound(final CannotFindAgentException exception) {
		return ResponseEntity
				.status(NOT_FOUND)
				.body(exception.getMessage());
	}

	@ExceptionHandler({ CannotFindRuleSetException.class })
	public ResponseEntity<Object> handleNoRuleSetFound(final CannotFindRuleSetException exception) {
		return ResponseEntity
				.status(NOT_FOUND)
				.body(exception.getMessage());
	}
}
