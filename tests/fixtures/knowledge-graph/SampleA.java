package tests.fixtures.knowledge_graph;

import java.util.List;
import java.util.ArrayList;

public class SampleA extends SampleB implements SampleInterface {
    private List<String> items;

    public SampleA(String value) {
        super(value);
        this.items = new ArrayList<>();
    }

    @Override
    public String process(String input) {
        String baseValue = getValue();
        int length = computeLength();
        return baseValue + input + length;
    }

    @Override
    public void reset() {
        items.clear();
    }

    public void addItem(String item) {
        items.add(item);
    }
}
