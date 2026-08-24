package restaurant;

import java.io.Serializable;

public class BookingResult implements Serializable {
    private final String orderId;
    private final String restaurantName;
    private final String dish;
    private final double price;
    private final String deliveryZone;

    public BookingResult(String orderId, String restaurantName, String dish,
                         double price, String deliveryZone) {
        this.orderId = orderId;
        this.restaurantName = restaurantName;
        this.dish = dish;
        this.price = price;
        this.deliveryZone = deliveryZone;
    }

    public String getOrderId() { return orderId; }
    public String getRestaurantName() { return restaurantName; }
    public String getDish() { return dish; }
    public double getPrice() { return price; }
    public String getDeliveryZone() { return deliveryZone; }
}