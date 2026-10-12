## 数据模型

### external user

```python
store.put_item(["external_user", follow_user_id], external_id, value)

namespace = ["external_user", follow_user_id]
key = external_id
value = {
    "external_id": external_id,         ## external_contact.external_userid
    "union_id": union_id,               ## external_contact.unionid
    "follow_user_id": follow_user_id,   ## follow_info.userid
    "name": name,                       ## external_contact.name
    "remark_name": remark_name          ## follow_info.remark
    "tags": tags                        ## follow_info.tag_id (仅id列表)
}
```


### tags setting

```python
store.put_item(["tags_setting"], tag_id, value)

namespace = ["tags_setting"]
key = tag_id
value = {
    "strategy_id": strategy_id,         ## tag_group.strategy_id, (默认 0，即：企业标签)
    "group_id": group_id,               ## tag_group.group_id
    "group_name": group_name,           ## tag_group.group_name
    "tag_id": tag_id,                   ## tag_group.tag.id
    "tag_name": tag_name,               ## tag_group.tag.name
    "deleted": deleted,                 ## tag_group.tag.deleted (默认 false)
    "version": version                  ## "" （默认空）
}
```

### 聊天消息

```python
store.put_item(["wxqy_msg", from_to_sorted_key], msg_id, value)

namespace = ["wxqy_msg", from_to_sorted_key]
key = msg_id
value = {
    "msg_id": msg_id,                   ## msgid
    "from_to_sorted_key": from_to_sorted_key    ## from、tolist中的ID，升序排列后拼接的值
    "from_id": from_id,                 ## from
    "to_id": to_id,                     ## tolist中的Id，仅当 tolist长度=1
    "YYYYMMDD": YYYYMMDD,               ## msgtime 格式化YYYYMMDD格式
    "msgtime": msgtime,                 ## msgtime
    "content": content                  ## content
    "seq": seq                          ## seq
}
```



### 客服消息

```python
store.put_item(["wxkf_msg", external_id], msg_id, value)

namespace = ["wxkf_msg", external_id]
key = msg_id
value = {
    "msg_id": msg_id,                   ## msgid
    "external_id": external_id          ## external_userid
    "open_kfid": open_kfid,             ## open_kfid
    "servicer_userid": servicer_userid, ## servicer_userid 可能为空
    "YYYYMMDD": YYYYMMDD,               ## send_time 格式化YYYYMMDD格式
    "msg_time": msgtime,                ## send_time
    "origin": origin,                   ## origin   仅当 origin = 3（客户发送）或者5（客服发送） 时有效
    "msg_type": msgtype,                ## msgtype  仅当 msgtype = "text" 时有效
    "content": content                  ## text.content 
}

```

### 微信小店订单

```python
store.put_item(["wxxd_order", union_id], order_id, value)

namespace = ["wxxd_order", union_id]
key = order_id
value = {
    "order_id": order_id,               ## order.order_id
    "open_id": open_id,                 ## order.openid
    "union_id": union_id,               ## order.unionid
    "order_status": order_status,       ## order.status
    "order_products": order_products,   ## order.order_detail.product_info[title]  多个商品组装成列表。
    "order_create_time": order_create_time,  ## order.create_time
    "YYYYMMDD": YYYYMMDD,               ## order_create_time 格式化成 YYYYMMDD格式
    "order_raw_detail": order_raw_detail  ## 原始的order json对象
}

```


## 参考接口

### 1、参考接口（批量获取客户详情） externalcontact/batch/get_by_user

参考接口返回的数据：

``` json
external_contact_list: [
{
    "external_contact": {
        "external_userid": "woAJ2GCAAAXtWyujaWJHDDGi0mACHBBB",
        "name": "王五",
        "position": "Engineer",
        "avatar": "http://p.qlogo.cn/bizmail/IcsdgagqefergqerhewSdage/0",
        "corp_name": "腾讯",
        "corp_full_name": "腾讯科技有限公司",
        "type": 2,
        "gender": 1,
        "unionid": "ozynqsulJFCZ2asdaf8h-nuasdAAA"
    },
    "follow_info": {
        "userid": "lisi",
        "remark": "王助理",
        "description": "采购问题咨询",
        "createtime": 1525881637,
        "tag_id": [
            "etAJ2GCAAAXtWyujaWJHDDGi0mACHAAA",
            "stJHDDGi0mAGi0mACHBBByujaW"
        ],
        "state": "外联二维码1",
        "oper_userid": "woAJ2GCAAAd1asdasdjO4wKmE8AabjBBB",
        "add_way": 3
    }
}]
```


### 2、参考接口（获取标签配置详情） 

企业标签：

```json
"tag_group": [
    {
        "group_id": "TAG_GROUPID1",
        "group_name": "GOURP_NAME",
        "create_time": 1557838797,
        "order": 1,
        "deleted": false,
        "tag": [
            {
                "id": "TAG_ID1",
                "name": "NAME1",
                "create_time": 1557838797,
                "order": 1,
                "deleted": false
            },
            {
                "id": "TAG_ID2",
                "name": "NAME2",
                "create_time": 1557838797,
                "order": 2,
                "deleted": true
            }
        ]
    }
]
```

企业规则组标签（根据配置文件获得strategy_id，仅获取AI项目下的规则组标签）
```json
"tag_group": [
    {
        "group_id": "TAG_GROUPID1",
        "group_name": "GOURP_NAME",
        "create_time": 1557838797,
        "order": 1,
        "strategy_id": 1,
        "tag": [
            {
                "id": "TAG_ID1",
                "name": "NAME1",
                "create_time": 1557838797,
                "order": 1
            },
            {
                "id": "TAG_ID2",
                "name": "NAME2",
                "create_time": 1557838797,
                "order": 2
            }
        ]
    }
]
```


### 3、参考接口（会话存档）

文本消息

```json
{
    "msgid": "CAQQluDa4QUY0On2rYSAgAMgzPrShAE=",
    "action": "send",
    "from": "XuJinSheng",
    "tolist": [
        "icefog"
    ],
    "roomid": "",
    "msgtime": 1547087894783,
    "msgtype": "text",
    "text": {
        "content": "test"
    }
}
```

消息撤回

```json
{
    "msgid": "15775510700152506326_1603875615",
    "action": "recall",
    "from": "kenshin",
    "tolist": [
        "wmUu0zBgAALV7ZymkcMyxvbTe8YdWxxA"
    ],
    "roomid": "",
    "msgtime": 1603875615723,
    "msgtype": "revoke",
    "revoke": {
        "pre_msgid": "14822339130656386894_1603875600"
    }
}
```



### 客服消息

```json
{
    "msgid": "B6zimULsHrvxaRQmLXoyUaoQNK",
    "open_kfid": "wkE8gRKQAAd4O8iGf3iB1QskRVG9BGEw",
    "external_userid": "wmE8gRKQAArnVDJ84bNuOK3KVjy_7-Wg",
    "send_time": 1752219971,
    "origin": 3,
    "msgtype": "text",
    "text": {
        "content": "哈哈哈"
    }
}
{
    "msgid": "7kA6tc2t4Xx8ptxKAUTW73tayNDftr6Q64PtenFxefrE",
    "send_time": 1752219997,
    "origin": 4,
    "msgtype": "event",
    "event": {
        "event_type": "session_status_change",
        "new_servicer_userid": "ChengJianZhang",
        "change_type": 1,
        "open_kfid": "wkE8gRKQAAd4O8iGf3iB1QskRVG9BGEw",
        "external_userid": "wmE8gRKQAArnVDJ84bNuOK3KVjy_7-Wg",
        "msg_code": "vfkBmnyd0WuE3FCo_uLkokeH5TUJFrBNa37HVEgqCFY"
    }
}
{
    "msgid": "h7zmbPKgRN3rRFCeC8Ge2evFWm1kQXXkwNigCC",
    "open_kfid": "wkE8gRKQAAd4O8iGf3iB1QskRVG9BGEw",
    "external_userid": "wmE8gRKQAArnVDJ84bNuOK3KVjy_7-Wg",
    "send_time": 1752222645,
    "origin": 5,
    "servicer_userid": "ChengJianZhang",
    "msgtype": "text",
    "text": {
        "content": "我是你的人工客服。"
    }
}
```

### 微信小店
```json

order: 
{
    "order_id": "3729377671362780672",
    "create_time": 1752057001,
    "update_time": 1752057026,
    "status": 20,
    "order_detail": {
        "product_infos": [
            {
                "product_id": "10000259513970",
                "sku_id": "3740020951",
                "thumb_img": "https://wst.wxapp.tc.qq.com/161/20304/snscosdownload/SH/reserved/6863792f0006811b0a1bf5cb7b61b01e000000a000004f50",
                "sale_price": 200,
                "sku_cnt": 1,
                "title": "创意手提袋",
                "on_aftersale_sku_cnt": 0,
                "finish_aftersale_sku_cnt": 0,
                "sku_code": "",
                "market_price": 200,
                "sku_attrs": [],
                "real_price": 200,
                "estimate_price": 200,
                "out_warehouse_id": "",
                "sku_deliver_info": {
                    "stock_type": 0
                },
                "extra_service": {
                    "seven_day_return": 1,
                    "freight_insurance": 0
                },
                "voucher_list": [],
                "order_product_coupon_info_list": [],
                "package_sku_list": [],
                "delivery_deadline": 1752229825,
                "merchant_discounted_price": 0,
                "finder_discounted_price": 0,
                "product_unique_id": "3729377671362780672_001"
            }
        ],
        "pay_info": {
            "payment_method": 1,
            "prepay_id": "up_wx09183002711256f9e6b3ee5cd769250001",
            "prepay_time": 1752057002,
            "pay_time": 1752057025,
            "transaction_id": "4332202460202507096307765602"
        },
        "price_info": {
            "product_price": 200,
            "order_price": 200,
            "freight": 0,
            "original_order_price": 200,
            "estimate_product_price": 200,
            "merchant_receieve_price": 200,
            "merchant_discounted_price": 0,
            "finder_discounted_price": 0
        },
        "delivery_info": {
            "address_info": {
                "user_name": "小*",
                "postal_code": "310013",
                "province_name": "浙江省",
                "city_name": "杭州市",
                "county_name": "西湖区",
                "detail_info": "****",
                "national_code": "888888",
                "tel_number": "136****6400",
                "house_number": "",
                "virtual_order_tel_number": "",
                "use_tel_number": 0,
                "hash_code": "5b994667d383dfb854f0aaf8523a9d6d"
            },
            "delivery_product_info": [],
            "ship_done_time": 0,
            "deliver_method": 0,
            "ewaybill_order_code": "ofMOFCa5sxDaK7c6c65aaWmatQRBwBmyBDYgZxb7pGkDBwALft-w_jCJzj0V6n7bi7_aP-LrXAAQ"
        },
        "ext_info": {
            "customer_notes": "",
            "merchant_notes": "",
            "order_scene": 1,
            "commission_handling_progress": 1
        },
        "commission_infos": [],
        "settle_info": {
            "predict_commission_fee": 2
        },
        "sku_sharer_infos": [],
        "source_infos": []
    },
    "aftersale_detail": {
        "aftersale_order_list": [],
        "on_aftersale_order_cnt": 0
    },
    "openid": "oaznn7LiPLrJczWq3zUMs1PR4p_0",
    "unionid": "ogV7R6x_GJOrD6HRghSyXQbhYFIA"
}

order: 
{
    "order_id": "3729349048931070720",
    "create_time": 1751947817,
    "update_time": 1752056923,
    "status": 200,
    "order_detail": {
        "product_infos": [
            {
                "product_id": "10000259513970",
                "sku_id": "3740020951",
                "thumb_img": "https://wst.wxapp.tc.qq.com/161/20304/snscosdownload/SH/reserved/6863792f0006811b0a1bf5cb7b61b01e000000a000004f50",
                "sale_price": 200,
                "sku_cnt": 1,
                "title": "创意手提袋",
                "on_aftersale_sku_cnt": 0,
                "finish_aftersale_sku_cnt": 1,
                "sku_code": "",
                "market_price": 200,
                "sku_attrs": [],
                "real_price": 200,
                "estimate_price": 200,
                "out_warehouse_id": "",
                "sku_deliver_info": {
                    "stock_type": 0
                },
                "extra_service": {
                    "seven_day_return": 1,
                    "freight_insurance": 0
                },
                "voucher_list": [],
                "order_product_coupon_info_list": [],
                "package_sku_list": [],
                "delivery_deadline": 1752120715,
                "merchant_discounted_price": 0,
                "finder_discounted_price": 0,
                "product_unique_id": "3729349048931070720_001"
            }
        ],
        "pay_info": {
            "payment_method": 1,
            "prepay_id": "up_wx08121018839320bbda7565617e8c020001",
            "prepay_time": 1751947819,
            "pay_time": 1751947915,
            "transaction_id": "4306002247202507085925267354"
        },
        "price_info": {
            "product_price": 200,
            "order_price": 200,
            "freight": 0,
            "original_order_price": 200,
            "estimate_product_price": 200,
            "merchant_receieve_price": 200,
            "merchant_discounted_price": 0,
            "finder_discounted_price": 0
        },
        "delivery_info": {
            "address_info": {
                "user_name": "大*",
                "postal_code": "311100",
                "province_name": "浙江省",
                "city_name": "杭州市",
                "county_name": "余杭区",
                "detail_info": "****",
                "national_code": "888888",
                "tel_number": "135****6404",
                "house_number": "",
                "virtual_order_tel_number": "",
                "use_tel_number": 0,
                "hash_code": "de240c5b714ef7ce0ac9112cde12d42c"
            },
            "delivery_product_info": [],
            "ship_done_time": 0,
            "deliver_method": 0,
            "ewaybill_order_code": "ofnnTnAyK7ltwgwRjb01IT4shDr1BKPZDIi5X7yKltvGGm98xvWnisXJRfOysZTysn1pQDwPQ3sg"
        },
        "ext_info": {
            "customer_notes": "",
            "merchant_notes": "",
            "order_scene": 1,
            "commission_handling_progress": 1
        },
        "commission_infos": [],
        "settle_info": {
            "predict_commission_fee": 0
        },
        "sku_sharer_infos": [],
        "source_infos": []
    },
    "aftersale_detail": {
        "aftersale_order_list": [
            {
                "aftersale_order_id": "2000002029991884",
                "status": 13
            }
        ],
        "on_aftersale_order_cnt": 0
    },
    "openid": "oaznn7JsSvZ-3prthpwkLts_vLR8",
    "unionid": "ogV7R6xyjHTUV0AMp4y7TbRbnmRk"
}
```

## 部署配置

1、配置可用于客户联系/AI销售助手的员工清单：user_id列表。

2、配置可用于AI助手（自建应用）身份创建的规则组ID。

3、配置默认的客服ID，并设定客服接待模式（员工接待）

