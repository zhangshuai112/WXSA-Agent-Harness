## 微信体系通知事件

### 企业微信-外部联系人事件

- MsgType： event
- Event： change_external_contact
- ChangeType：
    - edit_external_contact（编辑联系人）
    - add_external_contact（添加联系人）
    - add_half_external_contact（免验证添加联系人）
    - del_external_contact（删除外部联系人）
    - del_follow_user（被外部联系人删除）
    - transfer_fail（客户接替失败）



```xml
<xml>
	<ToUserName><![CDATA[toUser]]></ToUserName>
	<FromUserName><![CDATA[sys]]></FromUserName> 
	<CreateTime>1403610513</CreateTime>
	<MsgType><![CDATA[event]]></MsgType>
	<Event><![CDATA[change_external_contact]]></Event>
	<ChangeType><![CDATA[add_external_contact]]></ChangeType>
	<UserID><![CDATA[zhangsan]]></UserID>
	<ExternalUserID><![CDATA[woAJ2GCAAAXtWyujaWJHDDGi0mAAAA]]></ExternalUserID>
	<State><![CDATA[teststate]]></State>
	<WelcomeCode><![CDATA[WELCOMECODE]]></WelcomeCode>
</xml>
```



```xml
<xml>
	<ToUserName><![CDATA[toUser]]></ToUserName>
	<FromUserName><![CDATA[sys]]></FromUserName> 
	<CreateTime>1403610513</CreateTime>
	<MsgType><![CDATA[event]]></MsgType>
	<Event><![CDATA[change_external_contact]]></Event>
	<ChangeType><![CDATA[edit_external_contact]]></ChangeType>
	<UserID><![CDATA[zhangsan]]></UserID>
	<ExternalUserID><![CDATA[woAJ2GCAAAXtWyujaWJHDDGi0mAAAA]]></ExternalUserID>
</xml>
```




### 企业微信-标签设置事件

- MsgType： event
- Event： change_external_tag
- ChangeType：
    - create（创建企业标签）
    - update（更新企业标签）
    - delete（删除企业标签）
    - shuffle（标签顺序重排）


```xml
<xml>
	<ToUserName><![CDATA[CORPID]]></ToUserName>
	<FromUserName><![CDATA[sys]]></FromUserName> 
	<CreateTime>1403610513</CreateTime>
	<MsgType><![CDATA[event]]></MsgType>
	<Event><![CDATA[change_external_tag]]></Event>
	<Id><![CDATA[TAG_ID]]></Id>
	<TagType><![CDATA[tag]]></TagType>
	<ChangeType><![CDATA[create]]></ChangeType>
	<StrategyId>1</StrategyId>
</xml>
```

```xml
<xml>
	<ToUserName><![CDATA[CORPID]]></ToUserName>
	<FromUserName><![CDATA[sys]]></FromUserName> 
	<CreateTime>1403610513</CreateTime>
	<MsgType><![CDATA[event]]></MsgType>
	<Event><![CDATA[change_external_tag]]></Event>
	<Id><![CDATA[TAG_ID]]></Id>
	<TagType><![CDATA[tag]]></TagType>
	<ChangeType><![CDATA[delete]]></ChangeType>
	<StrategyId>1</StrategyId>
</xml>
```

### 企业微信-微信客服事件

- MsgType： event
- Event： kf_msg_or_event
- OpenKfId： {客服id}

```xml
<xml>
   <ToUserName><![CDATA[ww12345678910]]></ToUserName>
   <CreateTime>1348831860</CreateTime>
   <MsgType><![CDATA[event]]></MsgType>
   <Event><![CDATA[kf_msg_or_event]]></Event>
   <Token><![CDATA[ENCApHxnGDNAVNY4AaSJKj4Tb5mwsEMzxhFmHVGcra996NR]]></Token>
   <OpenKfId><![CDATA[wkxxxxxxx]]></OpenKfId>
</xml>
```

### 企业微信-会话存档事件

- MsgType： event
- Event： msgaudit_notify


```xml
<xml>
   <ToUserName><![CDATA[CorpID]]></ToUserName>
   <FromUserName><![CDATA[sys]]></FromUserName> 
   <CreateTime>1629101687</CreateTime>
   <MsgType><![CDATA[event]]></MsgType>
   <AgentID>2000004</AgentID>
   <Event><![CDATA[msgaudit_notify]]></Event>
</xml>
```

### 微信小店-订单事件

- MsgType： event
    - Event： channels_ec_order_new（订单下单）
    - Event： channels_ec_order_cancel（订单取消）
    - Event： channels_ec_order_pay（订单支付）
    - Event： channels_ec_order_wait_shipping（订单待发货）
    - Event： channels_ec_order_deliver（订单发货）
    - Event： channels_ec_order_confirm（确认收货）
    - Event： channels_ec_order_settle（结算成功）
    - Event： channels_ec_order_ext_info_update（其他信息更新）



```json
{
    "ToUserName": "gh_*", 
    "FromUserName": "OPENID", 
    "CreateTime": 1662480000, 
    "MsgType": "event", 
    "Event": "channels_ec_order_new", 
    "order_info": {
        "order_id": 3705115058471208928
    }
}
```

### 文档地址

#### 企业微信-外部联系人&标签事件
https://developer.work.weixin.qq.com/document/path/92130

#### 企业微信-微信客服消息事件
https://developer.work.weixin.qq.com/document/path/94670

#### 企业微信-会话存档事件
https://developer.work.weixin.qq.com/document/path/95039

#### 微信小店事件
https://developers.weixin.qq.com/doc/store/shop/product/order/order_status_graph.html