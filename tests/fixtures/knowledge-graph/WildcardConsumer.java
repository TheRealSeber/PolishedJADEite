package tests.fixtures.knowledge_graph;

import tests.fixtures.knowledge_graph.*;

public class WildcardConsumer {
    private SampleA a;
    private SampleB b;

    public WildcardConsumer() {
        this.a = new SampleA("test");
        this.b = new SampleB("other");
    }

    public String getFromA() {
        return a.getValue();
    }

    public int getFromB() {
        return b.computeLength();
    }
}
