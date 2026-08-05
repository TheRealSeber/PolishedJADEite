package tests.fixtures.knowledge_graph;

import java.io.Serializable;

public class SampleB implements Serializable {
    private String value;

    public SampleB(String value) {
        this.value = value;
    }

    public String getValue() {
        return value;
    }

    public int computeLength() {
        return value.length();
    }
}
