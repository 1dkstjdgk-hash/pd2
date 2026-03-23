#include <stdio.h>
double cm[7],kg[7];
int i,count1,count2,count3,count4,count5,count6;
double result1,result2,result3,result4; 


for(i=0;i<7,i++){
	printf("%d번째 학새의 키와 몸무게를 입력하시오:",i+1);
	scanf("%lf &lf",&cm[i],&kg[i]);
	
	if(cm[i]>= 168.0){
		count1+=1;
		result1 = count1/7.0;
	}
	else if(kg[i]>=58.0&&cm[i]>=168.0){
		count2+=1;
		result2 = count2/7.0
	}
	else if(kg[i>=58.0]||cm[i]>=168.0){
		if(kg[i]>=58.0&&cm[i]>=168.0){
		count3+=1;}
		else if(cm[i]>= 168.0){
			count4+=1;
		}
		result3 = count3/count4;
	}
	else if(cm[i]>=168.0||kg[i>=58.0]){
		if(kg[i]>=58.0){
			count5+=1;
		}
		else if(kg[i]>=58.0&&cm[i]>=168.0){
			count6+=1;
		}
		result4= count5/count6;
	}
	print("p(키>=168.0):%lf",result1);
	print("p(몸무게>=58.0,키>=168.0):%lf",result2);
	print("p(몸무게>=58.0|키>=168.0):%lf",result3);
	print("p(키>=168.0|몸무게>=58.0):%lf",result4);
} 
