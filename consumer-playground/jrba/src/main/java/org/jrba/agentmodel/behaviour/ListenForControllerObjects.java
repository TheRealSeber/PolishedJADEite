package org.jrba.agentmodel.behaviour;

import static java.util.Objects.isNull;
import static org.jrba.utils.agent.AgentConnector.connectAgentObject;

import java.util.List;
import java.util.function.Consumer;

import org.jrba.agentmodel.domain.AbstractAgent;

import jade.core.behaviours.Behaviour;
import jade.core.behaviours.CyclicBehaviour;

/**
 * Generic behaviour responsible for retrieving the controllers for a given agent
 */
public class ListenForControllerObjects extends CyclicBehaviour {

	private final AbstractAgent<?, ?> abstractAgent;
	private final List<Behaviour> initialBehaviours;
	private final int expectedControllersNo;
	private final Consumer<List<Behaviour>> initializeBehavioursMethod;
	private int objectCounter;

	/**
	 * Behaviour constructor.
	 *
	 * @param agent                 agent executing the behaviour
	 * @param initialBehaviours     initial behaviour for given agent
	 * @param expectedControllersNo expected number of controllers
	 */
	public ListenForControllerObjects(final AbstractAgent<?, ?> agent, final List<Behaviour> initialBehaviours,
			final int expectedControllersNo) {
		super(agent);
		this.abstractAgent = agent;
		this.initialBehaviours = initialBehaviours;
		this.objectCounter = 0;
		this.expectedControllersNo = expectedControllersNo;
		this.initializeBehavioursMethod = null;
	}

	/**
	 * Behaviour constructor.
	 *
	 * @param agent                      agent executing the behaviour
	 * @param initialBehaviours          initial behaviour for given agent
	 * @param expectedControllersNo      expected number of controllers
	 * @param initializeBehavioursMethod method used to override default behaviours initialization
	 */
	public ListenForControllerObjects(final AbstractAgent<?, ?> agent, final List<Behaviour> initialBehaviours,
			final int expectedControllersNo, final Consumer<List<Behaviour>> initializeBehavioursMethod) {
		super(agent);
		this.abstractAgent = agent;
		this.initialBehaviours = initialBehaviours;
		this.objectCounter = 0;
		this.expectedControllersNo = expectedControllersNo;
		this.initializeBehavioursMethod = initializeBehavioursMethod;
	}

	/**
	 * Method retrieves the controllers and stores it in agent class
	 */
	@Override
	public void action() {
		if (expectedControllersNo == 0) {
			addBehaviours();
		}

		else {
			final Object object = abstractAgent.getO2AObject();
			if (object != null) {
				connectAgentObject(abstractAgent, object);
				objectCounter++;

				if (objectCounter == expectedControllersNo) {
					addBehaviours();
				}
			} else {
				block();
			}
		}
	}

	private void addBehaviours() {
		if (isNull(initializeBehavioursMethod)) {
			initialBehaviours.forEach(abstractAgent::addBehaviour);
		} else {
			initializeBehavioursMethod.accept(initialBehaviours);
		}
		abstractAgent.removeBehaviour(this);
	}
}
